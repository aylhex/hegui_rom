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
set -u

mount -t proc none /proc
mount -t sysfs none /sys
mount -t tmpfs tmpfs /tmp
mount -t tmpfs tmpfs /run

# If this system was booted under UML, it will always have a /proc/exitcode
# file. If it was booted natively or under QEMU, it will not have this file.
if [[ -e /proc/exitcode ]]; then
  mount -t hostfs hostfs /host
else
  mount -t 9p -o trans=virtio,version=9p2000.L host /host
fi

test="$(sed -r 's/.*net_test=([^ ]*).*/\1/g' < /proc/cmdline)"
cd "$(dirname "${test}")"
./net_test.sh
poweroff -f
