#!/usr/bin/python
#
# Copyright 2017 The Android Open Source Project
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Test cases for device tree overlays for early mounting partitions."""

import os
import unittest


# Early mount fstab entry must have following properties defined.
REQUIRED_FSTAB_PROPERTIES = [
    'dev',
    'type',
    'mnt_flags',
    'fsmgr_flags',
]


def ReadFile(file_path):
  with open(file_path, 'r') as f:
    # Strip all trailing spaces, newline and null characters.
    return f.read().rstrip(' \n\x00')


def GetAndroidDtDir():
  """Returns location of android device tree directory."""
  with open('/proc/cmdline', 'r') as f:
    cmdline_list = f.read().split()

  # Find android device tree directory path passed through kernel cmdline.
  for option in cmdline_list:
    if option.startswith('androidboot.android_dt_dir'):
      return option.split('=')[1]

  # If no custom path found, return the default location.
  return '/proc/device-tree/firmware/android'


class DtEarlyMountTest(unittest.TestCase):
  """Test device tree overlays for early mounting."""

  def setUp(self):
    self._android_dt_dir = GetAndroidDtDir()
    self._fstab_dt_dir = os.path.join(self._android_dt_dir, 'fstab')

  def GetEarlyMountedPartitions(self):
    """Returns a list of partitions specified in fstab for early mount."""
    # Device tree nodes are represented as directories in the filesystem.
    return [x for x in os.listdir(self._fstab_dt_dir) if os.path.isdir(x)]

  def VerifyFstabEntry(self, partition):
    partition_dt_dir = os.path.join(self._fstab_dt_dir, partition)
    properties = [x for x in os.listdir(partition_dt_dir)]

    self.assertTrue(
        set(REQUIRED_FSTAB_PROPERTIES).issubset(properties),
        'fstab entry for /%s is missing required properties' % partition)

  def testFstabCompatible(self):
    """Verify fstab compatible string."""
    compatible = ReadFile(os.path.join(self._fstab_dt_dir, 'compatible'))
    self.assertEqual('android,fstab', compatible)

  def testFstabEntries(self):
    """Verify properties of early mount fstab entries."""
    for partition in self.GetEarlyMountedPartitions():
      self.VerifyFstabEntry(partition)

if __name__ == '__main__':
  unittest.main()

