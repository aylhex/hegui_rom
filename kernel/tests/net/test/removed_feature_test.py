#!/usr/bin/python
#
# Copyright 2016 The Android Open Source Project
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

import unittest

import gzip
import net_test


class RemovedFeatureTest(net_test.NetworkTest):
  KCONFIG = None

  @classmethod
  def loadKernelConfig(cls):
    cls.KCONFIG = {}
    with gzip.open('/proc/config.gz') as f:
      for line in f:
        line = line.strip()
        parts = line.split("=")
        if (len(parts) == 2):
          # Lines of the form:
          # CONFIG_FOO=y
          cls.KCONFIG[parts[0]] = parts[1]

  @classmethod
  def setUpClass(cls):
    cls.loadKernelConfig()

  def assertFeatureEnabled(self, featureName):
    return self.assertEqual("y", self.KCONFIG[featureName])

  def assertFeatureAbsent(self, featureName):
    return self.assertTrue(featureName not in self.KCONFIG)

  def testNetfilterRejectWithSocketError(self):
    """Verify that the CONFIG_IP{,6}_NF_TARGET_REJECT_SKERR option is gone.

       The commits to be reverted include:

           android-3.10: 6f489c42
           angler: 6f489c42
           bullhead: 6f489c42
           shamu: 6f489c42
           flounder: 6f489c42

       See b/28424847 and b/28719525 for more context.
    """
    self.assertFeatureEnabled("CONFIG_IP_NF_FILTER")
    self.assertFeatureEnabled("CONFIG_IP_NF_TARGET_REJECT")
    self.assertFeatureAbsent("CONFIG_IP_NF_TARGET_REJECT_SKERR")

    self.assertFeatureEnabled("CONFIG_IP6_NF_FILTER")
    self.assertFeatureEnabled("CONFIG_IP6_NF_TARGET_REJECT")
    self.assertFeatureAbsent("CONFIG_IP6_NF_TARGET_REJECT_SKERR")


if __name__ == "__main__":
  unittest.main()
