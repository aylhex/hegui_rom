#!/usr/bin/python
#
# Copyright 2018 The Android Open Source Project
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

import errno
from socket import *

import multinetwork_base
import net_test

_TEST_IP4_ADDR = "192.0.2.1"
_TEST_IP6_ADDR = "2001:db8::"


# Regression tests for interactions between kernel networking and netfilter
#
# These tests were added to ensure that the lookup path for local-ICMP errors
# do not cause failures. Specifically, local-ICMP packets do not have a
# net_device in the skb, and has been known to trigger bugs in surrounding code.
class NetilterRejectTargetTest(multinetwork_base.MultiNetworkBaseTest):

  def setUp(self):
    multinetwork_base.MultiNetworkBaseTest.setUp(self)
    net_test.RunIptablesCommand(4, "-A OUTPUT -d " + _TEST_IP4_ADDR + " -j REJECT")
    net_test.RunIptablesCommand(6, "-A OUTPUT -d " + _TEST_IP6_ADDR + " -j REJECT")

  def tearDown(self):
    net_test.RunIptablesCommand(4, "-D OUTPUT -d " + _TEST_IP4_ADDR + " -j REJECT")
    net_test.RunIptablesCommand(6, "-D OUTPUT -d " + _TEST_IP6_ADDR + " -j REJECT")
    multinetwork_base.MultiNetworkBaseTest.tearDown(self)

  # Test a rejected TCP connect. The responding ICMP may not have skb->dev set.
  # This tests the local-ICMP output-input path.
  def CheckRejectedTcp(self, version, addr):
    sock = net_test.TCPSocket(net_test.GetAddressFamily(version))
    netid = self.RandomNetid()
    self.SelectInterface(sock, netid, "mark")

    # Expect this to fail with ICMP unreachable
    try:
      sock.connect((addr, 53))
    except IOError:
      pass

  def testRejectTcp4(self):
    self.CheckRejectedTcp(4, _TEST_IP4_ADDR)

  def testRejectTcp6(self):
    self.CheckRejectedTcp(6, _TEST_IP6_ADDR)

  # Test a rejected UDP connect. The responding ICMP may not have skb->dev set.
  # This tests the local-ICMP output-input path.
  def CheckRejectedUdp(self, version, addr):
    sock = net_test.UDPSocket(net_test.GetAddressFamily(version))
    netid = self.RandomNetid()
    self.SelectInterface(sock, netid, "mark")

    # Expect this to fail with ICMP unreachable
    try:
      sock.sendto(net_test.UDP_PAYLOAD, (addr, 53))
    except IOError:
      pass

  def testRejectUdp4(self):
    self.CheckRejectedUdp(4, _TEST_IP4_ADDR)

  def testRejectUdp6(self):
    self.CheckRejectedUdp(6, _TEST_IP6_ADDR)


if __name__ == "__main__":
  unittest.main()