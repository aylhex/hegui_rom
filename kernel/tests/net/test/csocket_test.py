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

"""Unit tests for csocket."""

from socket import *  # pylint: disable=wildcard-import
import unittest

import csocket


LOOPBACK_IFINDEX = 1
SOL_IPV6 = 41


class CsocketTest(unittest.TestCase):

  def _BuildSocket(self, family, addr):
    s = socket(family, SOCK_DGRAM, 0)
    s.bind((addr, 0))
    return s

  def CheckRecvfrom(self, family, addr):
    s = self._BuildSocket(family, addr)
    addr = s.getsockname()
    sockaddr = csocket.Sockaddr(addr)
    s.sendto("foo", addr)
    data, addr = csocket.Recvfrom(s, 4096, 0)
    self.assertEqual("foo", data)
    self.assertEqual(sockaddr, addr)

    s.close()

  def testRecvfrom(self):
    self.CheckRecvfrom(AF_INET, "127.0.0.1")
    self.CheckRecvfrom(AF_INET6, "::1")

  def CheckRecvmsg(self, family, addr):
    s = self._BuildSocket(family, addr)

    if family == AF_INET:
      s.setsockopt(SOL_IP, csocket.IP_PKTINFO, 1)
      s.setsockopt(SOL_IP, csocket.IP_RECVTTL, 1)
      pktinfo_addr = inet_pton(AF_INET, addr)
      pktinfo = (SOL_IP, csocket.IP_PKTINFO,
                 csocket.InPktinfo((LOOPBACK_IFINDEX,
                                    pktinfo_addr, pktinfo_addr)))
      ttl = (SOL_IP, csocket.IP_TTL, 64)
    elif family == AF_INET6:
      s.setsockopt(SOL_IPV6, csocket.IPV6_RECVPKTINFO, 1)
      s.setsockopt(SOL_IPV6, csocket.IPV6_RECVHOPLIMIT, 1)
      pktinfo_addr = inet_pton(AF_INET6, addr)
      pktinfo = (SOL_IPV6, csocket.IPV6_PKTINFO,
                 csocket.In6Pktinfo((pktinfo_addr, LOOPBACK_IFINDEX)))
      ttl = (SOL_IPV6, csocket.IPV6_HOPLIMIT, 64)

    addr = s.getsockname()
    sockaddr = csocket.Sockaddr(addr)
    s.sendto("foo", addr)
    data, addr, cmsg = csocket.Recvmsg(s, 4096, 1024, 0)
    self.assertEqual("foo", data)
    self.assertEqual(sockaddr, addr)
    self.assertEqual([pktinfo, ttl], cmsg)

    s.close()

  def testRecvmsg(self):
    self.CheckRecvmsg(AF_INET, "127.0.0.1")
    self.CheckRecvmsg(AF_INET6, "::1")


if __name__ == "__main__":
  unittest.main()
