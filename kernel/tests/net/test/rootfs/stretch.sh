#!/bin/bash
#
# Copyright (C) 2018 The Android Open Source Project
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

set -e

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)

. $SCRIPT_DIR/common.sh

chroot_sanity_check

cd /root

# Add the needed debian sources
cat >/etc/apt/sources.list <<EOF
deb http://ftp.debian.org/debian stretch main
deb-src http://ftp.debian.org/debian stretch main
deb http://ftp.debian.org/debian stretch-backports main
deb-src http://ftp.debian.org/debian stretch-backports main
deb http://ftp.debian.org/debian buster main
deb-src http://ftp.debian.org/debian buster main
EOF

# Make sure apt doesn't want to install from buster by default
cat >/etc/apt/apt.conf.d/80default <<EOF
APT::Default-Release "stretch";
EOF

# Disable the automatic installation of recommended packages
cat >/etc/apt/apt.conf.d/90recommends <<EOF
APT::Install-Recommends "0";
EOF

# Deprioritize buster, so it must be specified manually
cat >/etc/apt/preferences.d/90buster <<EOF
Package: *
Pin: release a=buster
Pin-Priority: 90
EOF

# Update for the above changes
apt-get update

# Install python-scapy from buster, because stretch's version is broken
apt-get install -y -t buster python-scapy

# Note what we have installed; we will go back to this
LANG=C dpkg --get-selections | sort >originally-installed

# Install everything needed from stretch to build iptables
apt-get install -y \
  build-essential \
  autoconf \
  automake \
  bison \
  debhelper \
  devscripts \
  fakeroot \
  flex \
  libmnl-dev \
  libnetfilter-conntrack-dev \
  libnfnetlink-dev \
  libnftnl-dev \
  libtool

# Install newer linux-libc headers (these are from 4.16)
apt-get install -y -t stretch-backports linux-libc-dev

# We are done with apt; reclaim the disk space
apt-get clean

# Construct the iptables source package to build
iptables=iptables-1.6.1
mkdir -p /usr/src/$iptables

cd /usr/src/$iptables
# Download a specific revision of iptables from AOSP
aosp_iptables=android-wear-p-preview-2
wget -qO - \
  https://android.googlesource.com/platform/external/iptables/+archive/$aosp_iptables.tar.gz | \
  tar -zxf -
# Download a compatible 'debian' overlay from Debian salsa
# We don't want all of the sources, just the Debian modifications
debian_iptables=1.6.1-2_bpo9+1
debian_iptables_dir=pkg-iptables-debian-$debian_iptables
wget -qO - \
  https://salsa.debian.org/pkg-netfilter-team/pkg-iptables/-/archive/debian/$debian_iptables/$debian_iptables_dir.tar.gz | \
  tar --strip-components 1 -zxf - \
  $debian_iptables_dir/debian
cd -

cd /usr/src
# Generate a source package to leave in the filesystem. This is done for license
# compliance and build reproducibility.
tar --exclude=debian -cf - $iptables | \
  xz -9 >`echo $iptables | tr -s '-' '_'`.orig.tar.xz
cd -

cd /usr/src/$iptables
# Build debian packages from the integrated iptables source
dpkg-buildpackage -F -us -uc
cd -

# Record the list of packages we have installed now
LANG=C dpkg --get-selections | sort >installed

# Compute the difference, and remove anything installed between the snapshots
dpkg -P `comm -3 originally-installed installed | sed -e 's,install,,' -e 's,\t,,' | xargs`

cd /usr/src
# Find any packages generated, resolve to the debian package name, then
# exclude any compat, header or symbol packages
packages=`find -maxdepth 1 -name '*.deb' | colrm 1 2 | cut -d'_' -f1 |
          grep -ve '-compat$\|-dbg$\|-dbgsym$\|-dev$' | xargs`
# Install the patched iptables packages, and 'hold' then so
# "apt-get dist-upgrade" doesn't replace them
dpkg -i `
for package in $packages; do
  echo ${package}_*.deb
done | xargs`
for package in $packages; do
  echo "$package hold" | dpkg --set-selections
done
# Tidy up the mess we left behind, leaving just the source tarballs
rm -rf $iptables *.buildinfo *.changes *.deb *.dsc
cd -

# Ensure a getty is spawned on ttyS0, if booting the image manually
ln -s /lib/systemd/system/serial-getty\@.service \
  /etc/systemd/system/getty.target.wants/serial-getty\@ttyS0.service

# systemd needs some directories to be created
mkdir -p /var/lib/systemd/coredump /var/lib/systemd/rfkill

# Finalize and tidy up the created image
chroot_cleanup
