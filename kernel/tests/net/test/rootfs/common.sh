#!/bin/sh
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

chroot_sanity_check() {
  if [ ! -f /var/log/bootstrap.log ]; then
    echo "Do not run this script directly!"
    echo "This is supposed to be run from inside a debootstrap chroot!"
    echo "Aborting."
    exit 1
  fi
}

chroot_cleanup() {
  # Read-only root breaks booting via init
  cat >/etc/fstab << EOF
tmpfs /tmp     tmpfs defaults 0 0
tmpfs /var/log tmpfs defaults 0 0
tmpfs /var/tmp tmpfs defaults 0 0
EOF

  # systemd will attempt to re-create this symlink if it does not exist,
  # which fails if it is booting from a read-only root filesystem (which
  # is normally the case). The syslink must be relative, not absolute,
  # and it must point to /proc/self/mounts, not /proc/mounts.
  ln -sf ../proc/self/mounts /etc/mtab

  # Remove contaminants coming from the debootstrap process
  echo vm >/etc/hostname
  echo "nameserver 127.0.0.1" >/etc/resolv.conf

  # Put the helper net_test.sh script into place
  mv /root/net_test.sh /sbin/net_test.sh

  # Make sure the /host mountpoint exists for net_test.sh
  mkdir /host

  # Disable the root password
  passwd -d root

  # Clean up any junk created by the imaging process
  rm -rf /var/lib/apt/lists/* /var/log/bootstrap.log /root/* /tmp/*
  find /var/log -type f -exec rm -f '{}' ';'
}
