#!/usr/bin/python
#
# Copyright 2015 The Android Open Source Project
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

import itertools
import random
import unittest

from socket import *

import multinetwork_base
import net_test
import packets

class ForwardingTest(multinetwork_base.MultiNetworkBaseTest):
  TCP_TIME_WAIT = 6

  def ForwardBetweenInterfaces(self, enabled, iface1, iface2):
    for iif, oif in itertools.permutations([iface1, iface2]):
      self.iproute.IifRule(6, enabled, self.GetInterfaceName(iif),
                           self._TableForNetid(oif), self.PRIORITY_IIF)

  def setUp(self):
    self.SetSysctl("/proc/sys/net/ipv6/conf/all/forwarding", 1)

  def tearDown(self):
    self.SetSysctl("/proc/sys/net/ipv6/conf/all/forwarding", 0)

  """Checks that IPv6 forwarding works for UDP packets and is not broken by early demux.

  Relevant kernel commits:
    upstream:
      5425077d73e0c8e net: ipv6: Add early demux handler for UDP unicast
      0bd84065b19bca1 net: ipv6: Fix UDP early demux lookup with udp_l3mdev_accept=0
      Ifa9c2ddfaa5b51 net: ipv6: reset daddr and dport in sk if connect() fails
  """
  def CheckForwardingUdp(self, netid, iface1, iface2):
    # TODO: Make a test for IPv4
    # 1. Make version as an argument. Pick address to bind from array based
    #    on version.
    # 2. The prefix length of the address is hardcoded to /64. Use the subnet
    #    mask there instead.
    # 3. We recreate the address with SendRA, which obviously only works for
    #    IPv6. Use AddAddress for IPv4.

    # Create a UDP socket and bind to it
    version = 6
    s = net_test.UDPSocket(AF_INET6)
    self.SetSocketMark(s, netid)
    s.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
    s.bind(("::", 53))

    remoteaddr = self.GetRemoteAddress(version)
    myaddr = self.MyAddress(version, netid)

    try:
      # Delete address and check if packet is forwarded
      # (and not dropped because an incorrect socket match happened)
      self.iproute.DelAddress(myaddr, 64, self.ifindices[netid])
      hoplimit = 39
      desc, udp_pkt = packets.UDPWithOptions(version, myaddr, remoteaddr, 53)
      # Decrements the hoplimit of a packet to simulate forwarding.
      desc_fwded, udp_fwd = packets.UDPWithOptions(version, myaddr, remoteaddr,
                                                   53, hoplimit - 1)
      msg = "Sent %s, expected %s" % (desc, desc_fwded)
      self.ReceivePacketOn(iface1, udp_pkt)
      self.ExpectPacketOn(iface2, msg, udp_fwd)
    finally:
      # Recreate the address.
      self.SendRA(netid)
      s.close()

  """Checks that IPv6 forwarding doesn't crash the system.

  Relevant kernel commits:
    upstream net-next:
      e7eadb4 ipv6: inet6_sk() should use sk_fullsock()
    android-3.10:
      feee3c1 ipv6: inet6_sk() should use sk_fullsock()
      cdab04e net: add sk_fullsock() helper
    android-3.18:
      8246f18 ipv6: inet6_sk() should use sk_fullsock()
      bea19db net: add sk_fullsock() helper
  """
  def CheckForwardingCrashTcp(self, netid, iface1, iface2):
    version = 6
    listensocket = net_test.IPv6TCPSocket()
    self.SetSocketMark(listensocket, netid)
    listenport = net_test.BindRandomPort(version, listensocket)

    remoteaddr = self.GetRemoteAddress(version)
    myaddr = self.MyAddress(version, netid)

    desc, syn = packets.SYN(listenport, version, remoteaddr, myaddr)
    synack_desc, synack = packets.SYNACK(version, myaddr, remoteaddr, syn)
    msg = "Sent %s, expected %s" % (desc, synack_desc)
    reply = self._ReceiveAndExpectResponse(netid, syn, synack, msg)

    establishing_ack = packets.ACK(version, remoteaddr, myaddr, reply)[1]
    self.ReceivePacketOn(netid, establishing_ack)
    accepted, peer = listensocket.accept()
    remoteport = accepted.getpeername()[1]

    accepted.close()
    desc, fin = packets.FIN(version, myaddr, remoteaddr, establishing_ack)
    self.ExpectPacketOn(netid, msg + ": expecting %s after close" % desc, fin)

    desc, finack = packets.FIN(version, remoteaddr, myaddr, fin)
    self.ReceivePacketOn(netid, finack)

    # Check our socket is now in TIME_WAIT.
    sockets = self.ReadProcNetSocket("tcp6")
    mysrc = "%s:%04X" % (net_test.FormatSockStatAddress(myaddr), listenport)
    mydst = "%s:%04X" % (net_test.FormatSockStatAddress(remoteaddr), remoteport)
    state = None
    sockets = [s for s in sockets if s[0] == mysrc and s[1] == mydst]
    self.assertEquals(1, len(sockets))
    self.assertEquals("%02X" % self.TCP_TIME_WAIT, sockets[0][2])

    # Remove our IP address.
    try:
      self.iproute.DelAddress(myaddr, 64, self.ifindices[netid])

      self.ReceivePacketOn(iface1, finack)
      self.ReceivePacketOn(iface1, establishing_ack)
      self.ReceivePacketOn(iface1, establishing_ack)
      # No crashes? Good.

    finally:
      # Put back our IP address.
      self.SendRA(netid)
      listensocket.close()

  def CheckForwardingHandlerByProto(self, protocol, netid, iif, oif):
    if protocol == IPPROTO_UDP:
      self.CheckForwardingUdp(netid, iif, oif)
    elif protocol == IPPROTO_TCP:
      self.CheckForwardingCrashTcp(netid, iif, oif)
    else:
      raise NotImplementedError

  def CheckForwardingByProto(self, proto):
    # Run the test a few times as it doesn't crash/hang the first time.
    for netids in itertools.permutations(self.tuns):
      # Pick an interface to send traffic on and two to forward traffic between.
      netid, iface1, iface2 = random.sample(netids, 3)
      self.ForwardBetweenInterfaces(True, iface1, iface2)
      try:
        self.CheckForwardingHandlerByProto(proto, netid, iface1, iface2)
      finally:
        self.ForwardBetweenInterfaces(False, iface1, iface2)

  def testForwardingUdp(self):
    self.CheckForwardingByProto(IPPROTO_UDP)

  def testForwardingCrashTcp(self):
    self.CheckForwardingByProto(IPPROTO_TCP)

if __name__ == "__main__":
  unittest.main()
