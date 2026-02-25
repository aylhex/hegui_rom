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

import posix
import select
from socket import *  # pylint: disable=wildcard-import
import time
import unittest
from math import pow

import multinetwork_base

def accumulate(lis):
  total = 0
  for x in lis:
    total += x
    yield total

# This test attempts to validate time related behavior of the kernel
# under test and is therefore inherently prone to races. To avoid
# flakes, this test is biased to declare RFC 7559 RS backoff is
# present on the assumption that repeated runs will detect
# non-compliant kernels with high probability.
#
# If higher confidence is required, REQUIRED_SAMPLES and
# SAMPLE_INTERVAL can be increased at the cost of increased runtime.
class ResilientRouterSolicitationTest(multinetwork_base.MultiNetworkBaseTest):
  """Tests for IPv6 'resilient rs' RFC 7559 backoff behaviour.

  Relevant kernel commits:
    upstream:
      bd11f0741fa5 ipv6 addrconf: implement RFC7559 router solicitation backoff
    android-4.4:
      e246a2f11fcc UPSTREAM: ipv6 addrconf: implement RFC7559 router solicitation backoff

    android-4.1:
      c6e9a50816a0 UPSTREAM: ipv6 addrconf: implement RFC7559 router solicitation backoff

    android-3.18:
      2a7561c61417 UPSTREAM: ipv6 addrconf: implement RFC7559 router solicitation backoff

    android-3.10:
      ce2d59ac01f3 BACKPORT: ipv6 addrconf: implement RFC7559 router solicitation backoff

  """
  ROUTER_SOLICIT = 133

  _TEST_NETID = 123
  _PROC_NET_TUNABLE = "/proc/sys/net/ipv6/conf/%s/%s"

  @classmethod
  def setUpClass(cls):
    return

  def setUp(self):
    return

  @classmethod
  def tearDownClass(cls):
    return

  def tearDown(self):
    return

  @classmethod
  def isIPv6RouterSolicitation(cls, packet):
    return ((len(packet) >= 14 + 40 + 1) and
            # Use net_test.ETH_P_IPV6 here
            (ord(packet[12]) == 0x86) and
            (ord(packet[13]) == 0xdd) and
            (ord(packet[14]) >> 4 == 6) and
            (ord(packet[14 + 40]) == cls.ROUTER_SOLICIT))

  def makeTunInterface(self, netid):
    defaultDisableIPv6Path = self._PROC_NET_TUNABLE % ("default", "disable_ipv6")
    savedDefaultDisableIPv6 = self.GetSysctl(defaultDisableIPv6Path)
    self.SetSysctl(defaultDisableIPv6Path, 1)
    tun = self.CreateTunInterface(netid)
    self.SetSysctl(defaultDisableIPv6Path, savedDefaultDisableIPv6)
    return tun

  def testFeatureExists(self):
    return

  def testRouterSolicitationBackoff(self):
    # Test error tolerance
    EPSILON = 0.1
    # Minimum RFC3315 S14 backoff
    MIN_EXP = 1.9 - EPSILON
    # Maximum RFC3315 S14 backoff
    MAX_EXP = 2.1 + EPSILON
    SOLICITATION_INTERVAL = 1
    # Linear backoff for 4 samples yields 3.6 < T < 4.4
    # Exponential backoff for 4 samples yields 4.83 < T < 9.65
    REQUIRED_SAMPLES = 4
    # Give up after 10 seconds. Tuned for REQUIRED_SAMPLES = 4
    SAMPLE_INTERVAL = 10
    # Practically unlimited backoff
    SOLICITATION_MAX_INTERVAL = 1000
    MIN_LIN = SOLICITATION_INTERVAL * (0.9 - EPSILON)
    MAX_LIN = SOLICITATION_INTERVAL * (1.1 + EPSILON)
    netid = self._TEST_NETID
    tun = self.makeTunInterface(netid)
    poll = select.poll()
    poll.register(tun, select.POLLIN | select.POLLPRI)

    PROC_SETTINGS = [
        ("router_solicitation_delay", 1),
        ("router_solicitation_interval", SOLICITATION_INTERVAL),
        ("router_solicitation_max_interval", SOLICITATION_MAX_INTERVAL),
        ("router_solicitations", -1),
        ("disable_ipv6", 0)  # MUST be last
    ]

    iface = self.GetInterfaceName(netid)
    for tunable, value in PROC_SETTINGS:
      self.SetSysctl(self._PROC_NET_TUNABLE % (iface, tunable), value)

    start = time.time()
    deadline = start + SAMPLE_INTERVAL

    rsSendTimes = []
    while True:
      now = time.time();
      poll.poll((deadline - now) * 1000)
      try:
        packet = posix.read(tun.fileno(), 4096)
      except OSError:
        break

      txTime = time.time()
      if txTime > deadline:
        break;
      if not self.isIPv6RouterSolicitation(packet):
        continue

      # Record time relative to first router solicitation
      rsSendTimes.append(txTime - start)

      # Exit early if we have at least REQUIRED_SAMPLES
      if len(rsSendTimes) >= REQUIRED_SAMPLES:
        continue

    # Expect at least REQUIRED_SAMPLES router solicitations
    self.assertLessEqual(REQUIRED_SAMPLES, len(rsSendTimes))

    # Compute minimum and maximum bounds for RFC3315 S14 exponential backoff.
    # First retransmit is linear backoff, subsequent retransmits are exponential
    min_exp_bound = accumulate(map(lambda i: MIN_LIN * pow(MIN_EXP, i), range(0, len(rsSendTimes))))
    max_exp_bound = accumulate(map(lambda i: MAX_LIN * pow(MAX_EXP, i), range(0, len(rsSendTimes))))

    # Assert that each sample falls within the worst case interval. If all samples fit we accept
    # the exponential backoff hypothesis
    for (t, min_exp, max_exp) in zip(rsSendTimes[1:], min_exp_bound, max_exp_bound):
      self.assertLess(min_exp, t)
      self.assertGreater(max_exp, t)

if __name__ == "__main__":
  unittest.main()
