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

# NOTE: It is highly recommended that you do not create new wheezy rootfs
#       images. This script is here for forensic purposes only, to understand
#       how the original rootfs was created.

set -e

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)

. $SCRIPT_DIR/common.sh

chroot_sanity_check

# Remove things pulled in by debootstrap that we do not need
dpkg -P \
  debconf-i18n \
  liblocale-gettext-perl \
  libtext-charwidth-perl \
  libtext-iconv-perl \
  libtext-wrapi18n-perl \
  python2.6 \
  python2.6-minimal \
  xz-utils

# We are done with apt; reclaim the disk space
apt-get clean

# Ensure a getty is spawned on ttyS0, if booting the image manually
# This also removes the vt gettys, as we may have no vt
sed -i '/tty[123456]/d' /etc/inittab
echo "s0:1235:respawn:/sbin/getty 115200 ttyS0 linux" >>/etc/inittab

# Finalize and tidy up the created image
chroot_cleanup
