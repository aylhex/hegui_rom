#!/usr/bin/python
#
# Copyright 2014 The Android Open Source Project
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

import os
from socket import *  # pylint: disable=wildcard-import
import threading
import time
import unittest

import cstruct
import multinetwork_base
import net_test

IPV6_JOIN_ANYCAST = 27
IPV6_LEAVE_ANYCAST = 28

# pylint: disable=invalid-name
IPv6Mreq = cstruct.Struct("IPv6Mreq", "=16si", "multiaddr ifindex")


_CLOSE_HUNG = False


def CauseOops():
  open("/proc/sysrq-trigger", "w").write("c")


class CloseFileDescriptorThread(threading.Thread):

  def __init__(self, fd):
    super(CloseFileDescriptorThread, self).__init__()
    self.daemon = True
    self._fd = fd
    self.finished = False

  def run(self):
    global _CLOSE_HUNG
    _CLOSE_HUNG = True
    self._fd.close()
    _CLOSE_HUNG = False
    self.finished = True


class AnycastTest(multinetwork_base.MultiNetworkBaseTest):
  """Tests for IPv6 anycast addresses.

  Relevant kernel commits:
    upstream net-next:
      381f4dc ipv6: clean up anycast when an interface is destroyed

    android-3.10:
      86a47ad ipv6: clean up anycast when an interface is destroyed
  """
  _TEST_NETID = 123

  def AnycastSetsockopt(self, s, is_add, netid, addr):
    ifindex = self.ifindices[netid]
    self.assertTrue(ifindex)
    ipv6mreq = IPv6Mreq((addr, ifindex))
    option = IPV6_JOIN_ANYCAST if is_add else IPV6_LEAVE_ANYCAST
    s.setsockopt(IPPROTO_IPV6, option, ipv6mreq.Pack())

  def testAnycastNetdeviceUnregister(self):
    netid = self._TEST_NETID
    self.assertNotIn(netid, self.tuns)
    self.tuns[netid] = self.CreateTunInterface(netid)
    self.SendRA(netid)
    iface = self.GetInterfaceName(netid)
    self.ifindices[netid] = net_test.GetInterfaceIndex(iface)

    s = socket(AF_INET6, SOCK_DGRAM, 0)
    addr = self.MyAddress(6, netid)
    self.assertIsNotNone(addr)

    addr = inet_pton(AF_INET6, addr)
    addr = addr[:8] + os.urandom(8)
    self.AnycastSetsockopt(s, True, netid, addr)

    # Close the tun fd in the background.
    # This will hang if the kernel has the bug.
    thread = CloseFileDescriptorThread(self.tuns[netid])
    thread.start()
    # Wait up to 3 seconds for the thread to finish, but
    # continue and fail the test if the thread hangs.

    # For kernels with MPTCP ported, closing tun interface need more
    # than 0.5 sec. DAD procedure within MPTCP fullmesh module takes
    # more time, because duplicate address-timer takes a refcount
    # on the IPv6-address, preventing it from getting closed.
    thread.join(3)

    # Make teardown work.
    del self.tuns[netid]
    # Check that the interface is gone.
    try:
      self.assertIsNone(self.MyAddress(6, netid))
    finally:
      # This doesn't seem to help, but still.
      self.AnycastSetsockopt(s, False, netid, addr)
    self.assertTrue(thread.finished)


if __name__ == "__main__":
  unittest.main(exit=False)
  if _CLOSE_HUNG:
    time.sleep(3)
    CauseOops()
