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

import ctypes
import errno
import os
import random
from socket import *  # pylint: disable=wildcard-import
import struct
import time           # pylint: disable=unused-import
import unittest

from scapy import all as scapy

import csocket
import iproute
import multinetwork_base
import net_test
import packets

# For brevity.
UDP_PAYLOAD = net_test.UDP_PAYLOAD

IPV6_FLOWINFO = 11

SYNCOOKIES_SYSCTL = "/proc/sys/net/ipv4/tcp_syncookies"
TCP_MARK_ACCEPT_SYSCTL = "/proc/sys/net/ipv4/tcp_fwmark_accept"

# The IP[V6]UNICAST_IF socket option was added between 3.1 and 3.4.
HAVE_UNICAST_IF = net_test.LINUX_VERSION >= (3, 4, 0)

# RTPROT_RA is working properly with 4.14
HAVE_RTPROT_RA = net_test.LINUX_VERSION >= (4, 14, 0)

class ConfigurationError(AssertionError):
  pass


class OutgoingTest(multinetwork_base.MultiNetworkBaseTest):

  # How many times to run outgoing packet tests.
  ITERATIONS = 5

  def CheckPingPacket(self, version, netid, routing_mode, packet):
    s = self.BuildSocket(version, net_test.PingSocket, netid, routing_mode)

    myaddr = self.MyAddress(version, netid)
    mysockaddr = self.MySocketAddress(version, netid)
    s.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
    s.bind((mysockaddr, packets.PING_IDENT))
    net_test.SetSocketTos(s, packets.PING_TOS)

    dstaddr = self.GetRemoteAddress(version)
    dstsockaddr = self.GetRemoteSocketAddress(version)
    desc, expected = packets.ICMPEcho(version, myaddr, dstaddr)
    msg = "IPv%d ping: expected %s on %s" % (
        version, desc, self.GetInterfaceName(netid))

    s.sendto(packet + packets.PING_PAYLOAD, (dstsockaddr, 19321))

    self.ExpectPacketOn(netid, msg, expected)

  def CheckTCPSYNPacket(self, version, netid, routing_mode):
    s = self.BuildSocket(version, net_test.TCPSocket, netid, routing_mode)

    myaddr = self.MyAddress(version, netid)
    dstaddr = self.GetRemoteAddress(version)
    dstsockaddr = self.GetRemoteSocketAddress(version)
    desc, expected = packets.SYN(53, version, myaddr, dstaddr,
                                 sport=None, seq=None)


    # Non-blocking TCP connects always return EINPROGRESS.
    self.assertRaisesErrno(errno.EINPROGRESS, s.connect, (dstsockaddr, 53))
    msg = "IPv%s TCP connect: expected %s on %s" % (
        version, desc, self.GetInterfaceName(netid))
    self.ExpectPacketOn(netid, msg, expected)
    s.close()

  def CheckUDPPacket(self, version, netid, routing_mode):
    s = self.BuildSocket(version, net_test.UDPSocket, netid, routing_mode)

    myaddr = self.MyAddress(version, netid)
    dstaddr = self.GetRemoteAddress(version)
    dstsockaddr = self.GetRemoteSocketAddress(version)

    desc, expected = packets.UDP(version, myaddr, dstaddr, sport=None)
    msg = "IPv%s UDP %%s: expected %s on %s" % (
        version, desc, self.GetInterfaceName(netid))

    s.sendto(UDP_PAYLOAD, (dstsockaddr, 53))
    self.ExpectPacketOn(netid, msg % "sendto", expected)

    # IP_UNICAST_IF doesn't seem to work on connected sockets, so no TCP.
    if routing_mode != "ucast_oif":
      s.connect((dstsockaddr, 53))
      s.send(UDP_PAYLOAD)
      self.ExpectPacketOn(netid, msg % "connect/send", expected)
      s.close()

  def CheckRawGrePacket(self, version, netid, routing_mode):
    s = self.BuildSocket(version, net_test.RawGRESocket, netid, routing_mode)

    inner_version = {4: 6, 6: 4}[version]
    inner_src = self.MyAddress(inner_version, netid)
    inner_dst = self.GetRemoteAddress(inner_version)
    inner = str(packets.UDP(inner_version, inner_src, inner_dst, sport=None)[1])

    ethertype = {4: net_test.ETH_P_IP, 6: net_test.ETH_P_IPV6}[inner_version]
    # A GRE header can be as simple as two zero bytes and the ethertype.
    packet = struct.pack("!i", ethertype) + inner
    myaddr = self.MyAddress(version, netid)
    dstaddr = self.GetRemoteAddress(version)

    s.sendto(packet, (dstaddr, IPPROTO_GRE))
    desc, expected = packets.GRE(version, myaddr, dstaddr, ethertype, inner)
    msg = "Raw IPv%d GRE with inner IPv%d UDP: expected %s on %s" % (
        version, inner_version, desc, self.GetInterfaceName(netid))
    self.ExpectPacketOn(netid, msg, expected)

  def CheckOutgoingPackets(self, routing_mode):
    for _ in xrange(self.ITERATIONS):
      for netid in self.tuns:

        self.CheckPingPacket(4, netid, routing_mode, self.IPV4_PING)
        # Kernel bug.
        if routing_mode != "oif":
          self.CheckPingPacket(6, netid, routing_mode, self.IPV6_PING)

        # IP_UNICAST_IF doesn't seem to work on connected sockets, so no TCP.
        if routing_mode != "ucast_oif":
          self.CheckTCPSYNPacket(4, netid, routing_mode)
          self.CheckTCPSYNPacket(6, netid, routing_mode)
          self.CheckTCPSYNPacket(5, netid, routing_mode)

        self.CheckUDPPacket(4, netid, routing_mode)
        self.CheckUDPPacket(6, netid, routing_mode)
        self.CheckUDPPacket(5, netid, routing_mode)

        # Creating raw sockets on non-root UIDs requires properly setting
        # capabilities, which is hard to do from Python.
        # IP_UNICAST_IF is not supported on raw sockets.
        if routing_mode not in ["uid", "ucast_oif"]:
          self.CheckRawGrePacket(4, netid, routing_mode)
          self.CheckRawGrePacket(6, netid, routing_mode)

  def testMarkRouting(self):
    """Checks that socket marking selects the right outgoing interface."""
    self.CheckOutgoingPackets("mark")

  def testUidRouting(self):
    """Checks that UID routing selects the right outgoing interface."""
    self.CheckOutgoingPackets("uid")

  def testOifRouting(self):
    """Checks that oif routing selects the right outgoing interface."""
    self.CheckOutgoingPackets("oif")

  @unittest.skipUnless(HAVE_UNICAST_IF, "no support for UNICAST_IF")
  def testUcastOifRouting(self):
    """Checks that ucast oif routing selects the right outgoing interface."""
    self.CheckOutgoingPackets("ucast_oif")

  def CheckRemarking(self, version, use_connect):
    modes = ["mark", "oif", "uid"]
    # Setting UNICAST_IF on connected sockets does not work.
    if not use_connect and HAVE_UNICAST_IF:
      modes += ["ucast_oif"]

    for mode in modes:
      s = net_test.UDPSocket(self.GetProtocolFamily(version))

      # Figure out what packets to expect.
      sport = net_test.BindRandomPort(version, s)
      dstaddr = {4: self.IPV4_ADDR, 6: self.IPV6_ADDR}[version]
      unspec = {4: "0.0.0.0", 6: "::"}[version]  # Placeholder.
      desc, expected = packets.UDP(version, unspec, dstaddr, sport)

      # If we're testing connected sockets, connect the socket on the first
      # netid now.
      if use_connect:
        netid = self.tuns.keys()[0]
        self.SelectInterface(s, netid, mode)
        s.connect((dstaddr, 53))
        expected.src = self.MyAddress(version, netid)

      # For each netid, select that network without closing the socket, and
      # check that the packets sent on that socket go out on the right network.
      #
      # For connected sockets, routing is cached in the socket's destination
      # cache entry. In this case, we check that just re-selecting the netid
      # (except via SO_BINDTODEVICE) does not change routing, but that
      # subsequently invalidating the destination cache entry does. Arguably
      # this is a bug in the kernel because re-selecting the netid should cause
      # routing to change. But it is a convenient way to check that
      # InvalidateDstCache actually works.
      prevnetid = None
      for netid in self.tuns:
        self.SelectInterface(s, netid, mode)
        if not use_connect:
          expected.src = self.MyAddress(version, netid)

        def ExpectSendUsesNetid(netid):
          connected_str = "Connected" if use_connect else "Unconnected"
          msg = "%s UDPv%d socket remarked using %s: expecting %s on %s" % (
              connected_str, version, mode, desc, self.GetInterfaceName(netid))
          if use_connect:
            s.send(UDP_PAYLOAD)
          else:
            s.sendto(UDP_PAYLOAD, (dstaddr, 53))
          self.ExpectPacketOn(netid, msg, expected)

        if use_connect and mode in ["mark", "uid", "ucast_oif"]:
          # If we have a destination cache entry, packets are not rerouted...
          if prevnetid:
            ExpectSendUsesNetid(prevnetid)
            # ... until we invalidate it.
            self.InvalidateDstCache(version, prevnetid)
          ExpectSendUsesNetid(netid)
        else:
          ExpectSendUsesNetid(netid)

        self.SelectInterface(s, None, mode)
        prevnetid = netid

  def testIPv4Remarking(self):
    """Checks that updating the mark on an IPv4 socket changes routing."""
    self.CheckRemarking(4, False)
    self.CheckRemarking(4, True)

  def testIPv6Remarking(self):
    """Checks that updating the mark on an IPv6 socket changes routing."""
    self.CheckRemarking(6, False)
    self.CheckRemarking(6, True)

  def testIPv6StickyPktinfo(self):
    for _ in xrange(self.ITERATIONS):
      for netid in self.tuns:
        s = net_test.UDPSocket(AF_INET6)

        # Set a flowlabel.
        net_test.SetFlowLabel(s, net_test.IPV6_ADDR, 0xdead)
        s.setsockopt(net_test.SOL_IPV6, net_test.IPV6_FLOWINFO_SEND, 1)

        # Set some destination options.
        nonce = "\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\x0c"
        dstopts = "".join([
            "\x11\x02",              # Next header=UDP, 24 bytes of options.
            "\x01\x06", "\x00" * 6,  # PadN, 6 bytes of padding.
            "\x8b\x0c",              # ILNP nonce, 12 bytes.
            nonce
        ])
        s.setsockopt(net_test.SOL_IPV6, IPV6_DSTOPTS, dstopts)
        s.setsockopt(net_test.SOL_IPV6, IPV6_UNICAST_HOPS, 255)

        pktinfo = multinetwork_base.MakePktInfo(6, None, self.ifindices[netid])

        # Set the sticky pktinfo option.
        s.setsockopt(net_test.SOL_IPV6, IPV6_PKTINFO, pktinfo)

        # Specify the flowlabel in the destination address.
        s.sendto(UDP_PAYLOAD, (net_test.IPV6_ADDR, 53, 0xdead, 0))

        sport = s.getsockname()[1]
        srcaddr = self.MyAddress(6, netid)
        expected = (scapy.IPv6(src=srcaddr, dst=net_test.IPV6_ADDR,
                               fl=0xdead, hlim=255) /
                    scapy.IPv6ExtHdrDestOpt(
                        options=[scapy.PadN(optdata="\x00\x00\x00\x00\x00\x00"),
                                 scapy.HBHOptUnknown(otype=0x8b,
                                                     optdata=nonce)]) /
                    scapy.UDP(sport=sport, dport=53) /
                    UDP_PAYLOAD)
        msg = "IPv6 UDP using sticky pktinfo: expected UDP packet on %s" % (
            self.GetInterfaceName(netid))
        self.ExpectPacketOn(netid, msg, expected)

  def CheckPktinfoRouting(self, version):
    for _ in xrange(self.ITERATIONS):
      for netid in self.tuns:
        family = self.GetProtocolFamily(version)
        s = net_test.UDPSocket(family)

        if version == 6:
          # Create a flowlabel so we can use it.
          net_test.SetFlowLabel(s, net_test.IPV6_ADDR, 0xbeef)

          # Specify some arbitrary options.
          # We declare the flowlabel as ctypes.c_uint32 because on a 32-bit
          # Python interpreter an integer greater than 0x7fffffff (such as our
          # chosen flowlabel after being passed through htonl) is converted to
          # long, and _MakeMsgControl doesn't know what to do with longs.
          cmsgs = [
              (net_test.SOL_IPV6, IPV6_HOPLIMIT, 39),
              (net_test.SOL_IPV6, IPV6_TCLASS, 0x83),
              (net_test.SOL_IPV6, IPV6_FLOWINFO, ctypes.c_uint(htonl(0xbeef))),
          ]
        else:
          # Support for setting IPv4 TOS and TTL via cmsg only appeared in 3.13.
          cmsgs = []
          s.setsockopt(net_test.SOL_IP, IP_TTL, 39)
          s.setsockopt(net_test.SOL_IP, IP_TOS, 0x83)

        dstaddr = self.GetRemoteAddress(version)
        self.SendOnNetid(version, s, dstaddr, 53, netid, UDP_PAYLOAD, cmsgs)

        sport = s.getsockname()[1]
        srcaddr = self.MyAddress(version, netid)

        desc, expected = packets.UDPWithOptions(version, srcaddr, dstaddr,
                                                sport=sport)

        msg = "IPv%d UDP using pktinfo routing: expected %s on %s" % (
            version, desc, self.GetInterfaceName(netid))
        self.ExpectPacketOn(netid, msg, expected)

  def testIPv4PktinfoRouting(self):
    self.CheckPktinfoRouting(4)

  def testIPv6PktinfoRouting(self):
    self.CheckPktinfoRouting(6)


class MarkTest(multinetwork_base.InboundMarkingTest):

  def CheckReflection(self, version, gen_packet, gen_reply):
    """Checks that replies go out on the same interface as the original.

    For each combination:
     - Calls gen_packet to generate a packet to that IP address.
     - Writes the packet generated by gen_packet on the given tun
       interface, causing the kernel to receive it.
     - Checks that the kernel's reply matches the packet generated by
       gen_reply.

    Args:
      version: An integer, 4 or 6.
      gen_packet: A function taking an IP version (an integer), a source
        address and a destination address (strings), and returning a scapy
        packet.
      gen_reply: A function taking the same arguments as gen_packet,
        plus a scapy packet, and returning a scapy packet.
    """
    for netid, iif, ip_if, myaddr, remoteaddr in self.Combinations(version):
      # Generate a test packet.
      desc, packet = gen_packet(version, remoteaddr, myaddr)

      # Test with mark reflection enabled and disabled.
      for reflect in [0, 1]:
        self.SetMarkReflectSysctls(reflect)
        # HACK: IPv6 ping replies always do a routing lookup with the
        # interface the ping came in on. So even if mark reflection is not
        # working, IPv6 ping replies will be properly reflected. Don't
        # fail when that happens.
        if reflect or desc == "ICMPv6 echo":
          reply_desc, reply = gen_reply(version, myaddr, remoteaddr, packet)
        else:
          reply_desc, reply = None, None

        msg = self._FormatMessage(iif, ip_if, "reflect=%d" % reflect,
                                  desc, reply_desc)
        self._ReceiveAndExpectResponse(netid, packet, reply, msg)

  def SYNToClosedPort(self, *args):
    return packets.SYN(999, *args)

  def testIPv4ICMPErrorsReflectMark(self):
    self.CheckReflection(4, packets.UDP, packets.ICMPPortUnreachable)

  def testIPv6ICMPErrorsReflectMark(self):
    self.CheckReflection(6, packets.UDP, packets.ICMPPortUnreachable)

  def testIPv4PingRepliesReflectMarkAndTos(self):
    self.CheckReflection(4, packets.ICMPEcho, packets.ICMPReply)

  def testIPv6PingRepliesReflectMarkAndTos(self):
    self.CheckReflection(6, packets.ICMPEcho, packets.ICMPReply)

  def testIPv4RSTsReflectMark(self):
    self.CheckReflection(4, self.SYNToClosedPort, packets.RST)

  def testIPv6RSTsReflectMark(self):
    self.CheckReflection(6, self.SYNToClosedPort, packets.RST)


class TCPAcceptTest(multinetwork_base.InboundMarkingTest):

  MODE_BINDTODEVICE = "SO_BINDTODEVICE"
  MODE_INCOMING_MARK = "incoming mark"
  MODE_EXPLICIT_MARK = "explicit mark"
  MODE_UID = "uid"

  @classmethod
  def setUpClass(cls):
    super(TCPAcceptTest, cls).setUpClass()

    # Open a port so we can observe SYN+ACKs. Since it's a dual-stack socket it
    # will accept both IPv4 and IPv6 connections. We do this here instead of in
    # each test so we can use the same socket every time. That way, if a kernel
    # bug causes incoming packets to mark the listening socket instead of the
    # accepted socket, the test will fail as soon as the next address/interface
    # combination is tried.
    cls.listensocket = net_test.IPv6TCPSocket()
    cls.listenport = net_test.BindRandomPort(6, cls.listensocket)

  def _SetTCPMarkAcceptSysctl(self, value):
    self.SetSysctl(TCP_MARK_ACCEPT_SYSCTL, value)

  def CheckTCPConnection(self, mode, listensocket, netid, version,
                         myaddr, remoteaddr, packet, reply, msg):
    establishing_ack = packets.ACK(version, remoteaddr, myaddr, reply)[1]

    # Attempt to confuse the kernel.
    self.InvalidateDstCache(version, netid)

    self.ReceivePacketOn(netid, establishing_ack)

    # If we're using UID routing, the accept() call has to be run as a UID that
    # is routed to the specified netid, because the UID of the socket returned
    # by accept() is the effective UID of the process that calls it. It doesn't
    # need to be the same UID; any UID that selects the same interface will do.
    with net_test.RunAsUid(self.UidForNetid(netid)):
      s, _ = listensocket.accept()

    try:
      # Check that data sent on the connection goes out on the right interface.
      desc, data = packets.ACK(version, myaddr, remoteaddr, establishing_ack,
                               payload=UDP_PAYLOAD)
      s.send(UDP_PAYLOAD)
      self.ExpectPacketOn(netid, msg + ": expecting %s" % desc, data)
      self.InvalidateDstCache(version, netid)

      # Keep up our end of the conversation.
      ack = packets.ACK(version, remoteaddr, myaddr, data)[1]
      self.InvalidateDstCache(version, netid)
      self.ReceivePacketOn(netid, ack)

      mark = self.GetSocketMark(s)
    finally:
      self.InvalidateDstCache(version, netid)
      s.close()
      self.InvalidateDstCache(version, netid)

    if mode == self.MODE_INCOMING_MARK:
      self.assertEquals(netid, mark & self.NETID_FWMASK,
                        msg + ": Accepted socket: Expected mark %d, got %d" % (
                            netid, mark))
    elif mode != self.MODE_EXPLICIT_MARK:
      self.assertEquals(0, self.GetSocketMark(listensocket))

    # Check the FIN was sent on the right interface, and ack it. We don't expect
    # this to fail because by the time the connection is established things are
    # likely working, but a) extra tests are always good and b) extra packets
    # like the FIN (and retransmitted FINs) could cause later tests that expect
    # no packets to fail.
    desc, fin = packets.FIN(version, myaddr, remoteaddr, ack)
    self.ExpectPacketOn(netid, msg + ": expecting %s after close" % desc, fin)

    desc, finack = packets.FIN(version, remoteaddr, myaddr, fin)
    self.ReceivePacketOn(netid, finack)

    # Since we called close() earlier, the userspace socket object is gone, so
    # the socket has no UID. If we're doing UID routing, the ack might be routed
    # incorrectly. Not much we can do here.
    desc, finackack = packets.ACK(version, myaddr, remoteaddr, finack)
    self.ExpectPacketOn(netid, msg + ": expecting final ack", finackack)

  def CheckTCP(self, version, modes):
    """Checks that incoming TCP connections work.

    Args:
      version: An integer, 4 or 6.
      modes: A list of modes to excercise.
    """
    for syncookies in [0, 2]:
      for mode in modes:
        for netid, iif, ip_if, myaddr, remoteaddr in self.Combinations(version):
          listensocket = self.listensocket
          listenport = listensocket.getsockname()[1]

          accept_sysctl = 1 if mode == self.MODE_INCOMING_MARK else 0
          self._SetTCPMarkAcceptSysctl(accept_sysctl)
          self.SetMarkReflectSysctls(accept_sysctl)

          bound_dev = iif if mode == self.MODE_BINDTODEVICE else None
          self.BindToDevice(listensocket, bound_dev)

          mark = netid if mode == self.MODE_EXPLICIT_MARK else 0
          self.SetSocketMark(listensocket, mark)

          uid = self.UidForNetid(netid) if mode == self.MODE_UID else 0
          os.fchown(listensocket.fileno(), uid, -1)

          # Generate the packet here instead of in the outer loop, so
          # subsequent TCP connections use different source ports and
          # retransmissions from old connections don't confuse subsequent
          # tests.
          desc, packet = packets.SYN(listenport, version, remoteaddr, myaddr)

          if mode:
            reply_desc, reply = packets.SYNACK(version, myaddr, remoteaddr,
                                               packet)
          else:
            reply_desc, reply = None, None

          extra = "mode=%s, syncookies=%d" % (mode, syncookies)
          msg = self._FormatMessage(iif, ip_if, extra, desc, reply_desc)
          reply = self._ReceiveAndExpectResponse(netid, packet, reply, msg)
          if reply:
            self.CheckTCPConnection(mode, listensocket, netid, version, myaddr,
                                    remoteaddr, packet, reply, msg)

  def testBasicTCP(self):
    self.CheckTCP(4, [None, self.MODE_BINDTODEVICE, self.MODE_EXPLICIT_MARK])
    self.CheckTCP(6, [None, self.MODE_BINDTODEVICE, self.MODE_EXPLICIT_MARK])

  def testIPv4MarkAccept(self):
    self.CheckTCP(4, [self.MODE_INCOMING_MARK])

  def testIPv6MarkAccept(self):
    self.CheckTCP(6, [self.MODE_INCOMING_MARK])

  def testIPv4UidAccept(self):
    self.CheckTCP(4, [self.MODE_UID])

  def testIPv6UidAccept(self):
    self.CheckTCP(6, [self.MODE_UID])

  def testIPv6ExplicitMark(self):
    self.CheckTCP(6, [self.MODE_EXPLICIT_MARK])

@unittest.skipUnless(multinetwork_base.HAVE_AUTOCONF_TABLE,
                     "need support for per-table autoconf")
class RIOTest(multinetwork_base.MultiNetworkBaseTest):
  """Test for IPv6 RFC 4191 route information option

  Relevant kernel commits:
    upstream:
      f104a567e673 ipv6: use rt6_get_dflt_router to get default router in rt6_route_rcv
      bbea124bc99d net: ipv6: Add sysctl for minimum prefix len acceptable in RIOs.

    android-4.9:
      d860b2e8a7f1 FROMLIST: net: ipv6: Add sysctl for minimum prefix len acceptable in RIOs

    android-4.4:
      e953f89b8563 net: ipv6: Add sysctl for minimum prefix len acceptable in RIOs.

    android-4.1:
      84f2f47716cd net: ipv6: Add sysctl for minimum prefix len acceptable in RIOs.

    android-3.18:
      65f8936934fa net: ipv6: Add sysctl for minimum prefix len acceptable in RIOs.

    android-3.10:
      161e88ebebc7 net: ipv6: Add sysctl for minimum prefix len acceptable in RIOs.

  """

  def setUp(self):
    super(RIOTest, self).setUp()
    self.NETID = random.choice(self.NETIDS)
    self.IFACE = self.GetInterfaceName(self.NETID)
    # return min/max plen to default values before each test case
    self.SetAcceptRaRtInfoMinPlen(0)
    self.SetAcceptRaRtInfoMaxPlen(0)

  def GetRoutingTable(self):
    return self._TableForNetid(self.NETID)

  def SetAcceptRaRtInfoMinPlen(self, plen):
    self.SetSysctl(
        "/proc/sys/net/ipv6/conf/%s/accept_ra_rt_info_min_plen"
        % self.IFACE, plen)

  def GetAcceptRaRtInfoMinPlen(self):
    return int(self.GetSysctl(
        "/proc/sys/net/ipv6/conf/%s/accept_ra_rt_info_min_plen" % self.IFACE))

  def SetAcceptRaRtInfoMaxPlen(self, plen):
    self.SetSysctl(
        "/proc/sys/net/ipv6/conf/%s/accept_ra_rt_info_max_plen"
        % self.IFACE, plen)

  def GetAcceptRaRtInfoMaxPlen(self):
    return int(self.GetSysctl(
        "/proc/sys/net/ipv6/conf/%s/accept_ra_rt_info_max_plen" % self.IFACE))

  def SendRIO(self, rtlifetime, plen, prefix, prf):
    options = scapy.ICMPv6NDOptRouteInfo(rtlifetime=rtlifetime, plen=plen,
                                         prefix=prefix, prf=prf)
    self.SendRA(self.NETID, options=(options,))

  def FindRoutesWithDestination(self, destination):
    canonical = net_test.CanonicalizeIPv6Address(destination)
    return [r for _, r in self.iproute.DumpRoutes(6, self.GetRoutingTable())
            if ('RTA_DST' in r and r['RTA_DST'] == canonical)]

  def FindRoutesWithGateway(self):
    return [r for _, r in self.iproute.DumpRoutes(6, self.GetRoutingTable())
            if 'RTA_GATEWAY' in r]

  def CountRoutes(self):
    return len(self.iproute.DumpRoutes(6, self.GetRoutingTable()))

  def GetRouteExpiration(self, route):
    return float(route['RTA_CACHEINFO'].expires) / 100.0

  def AssertExpirationInRange(self, routes, lifetime, epsilon):
    self.assertTrue(routes)
    found = False
    # Assert that at least one route in routes has the expected lifetime
    for route in routes:
      expiration = self.GetRouteExpiration(route)
      if expiration < lifetime - epsilon:
        continue
      if expiration > lifetime + epsilon:
        continue
      found = True
    self.assertTrue(found)

  def DelRA6(self, prefix, plen):
    version = 6
    netid = self.NETID
    table = self._TableForNetid(netid)
    router = self._RouterAddress(netid, version)
    ifindex = self.ifindices[netid]
    # We actually want to specify RTPROT_RA, however an upstream
    # kernel bug causes RAs to be installed with RTPROT_BOOT.
    if HAVE_RTPROT_RA:
       rtprot = iproute.RTPROT_RA
    else:
       rtprot = iproute.RTPROT_BOOT
    self.iproute._Route(version, rtprot, iproute.RTM_DELROUTE,
                        table, prefix, plen, router, ifindex, None, None)

  def testSetAcceptRaRtInfoMinPlen(self):
    for plen in xrange(-1, 130):
      self.SetAcceptRaRtInfoMinPlen(plen)
      self.assertEquals(plen, self.GetAcceptRaRtInfoMinPlen())

  def testSetAcceptRaRtInfoMaxPlen(self):
    for plen in xrange(-1, 130):
      self.SetAcceptRaRtInfoMaxPlen(plen)
      self.assertEquals(plen, self.GetAcceptRaRtInfoMaxPlen())

  def testZeroRtLifetime(self):
    PREFIX = "2001:db8:8901:2300::"
    RTLIFETIME = 73500
    PLEN = 56
    PRF = 0
    self.SetAcceptRaRtInfoMaxPlen(PLEN)
    self.SendRIO(RTLIFETIME, PLEN, PREFIX, PRF)
    # Give the kernel time to notice our RA
    time.sleep(0.01)
    self.assertTrue(self.FindRoutesWithDestination(PREFIX))
    # RIO with rtlifetime = 0 should remove from routing table
    self.SendRIO(0, PLEN, PREFIX, PRF)
    # Give the kernel time to notice our RA
    time.sleep(0.01)
    self.assertFalse(self.FindRoutesWithDestination(PREFIX))

  def testMinPrefixLenRejection(self):
    PREFIX = "2001:db8:8902:2345::"
    RTLIFETIME = 70372
    PRF = 0
    # sweep from high to low to avoid spurious failures from late arrivals.
    for plen in xrange(130, 1, -1):
      self.SetAcceptRaRtInfoMinPlen(plen)
      # RIO with plen < min_plen should be ignored
      self.SendRIO(RTLIFETIME, plen - 1, PREFIX, PRF)
    # Give the kernel time to notice our RAs
    time.sleep(0.1)
    # Expect no routes
    routes = self.FindRoutesWithDestination(PREFIX)
    self.assertFalse(routes)

  def testMaxPrefixLenRejection(self):
    PREFIX = "2001:db8:8903:2345::"
    RTLIFETIME = 73078
    PRF = 0
    # sweep from low to high to avoid spurious failures from late arrivals.
    for plen in xrange(-1, 128, 1):
      self.SetAcceptRaRtInfoMaxPlen(plen)
      # RIO with plen > max_plen should be ignored
      self.SendRIO(RTLIFETIME, plen + 1, PREFIX, PRF)
    # Give the kernel time to notice our RAs
    time.sleep(0.1)
    # Expect no routes
    routes = self.FindRoutesWithDestination(PREFIX)
    self.assertFalse(routes)

  def testSimpleAccept(self):
    PREFIX = "2001:db8:8904:2345::"
    RTLIFETIME = 9993
    PRF = 0
    PLEN = 56
    self.SetAcceptRaRtInfoMinPlen(48)
    self.SetAcceptRaRtInfoMaxPlen(64)
    self.SendRIO(RTLIFETIME, PLEN, PREFIX, PRF)
    # Give the kernel time to notice our RA
    time.sleep(0.01)
    routes = self.FindRoutesWithGateway()
    self.AssertExpirationInRange(routes, RTLIFETIME, 1)
    self.DelRA6(PREFIX, PLEN)

  def testEqualMinMaxAccept(self):
    PREFIX = "2001:db8:8905:2345::"
    RTLIFETIME = 6326
    PLEN = 21
    PRF = 0
    self.SetAcceptRaRtInfoMinPlen(PLEN)
    self.SetAcceptRaRtInfoMaxPlen(PLEN)
    self.SendRIO(RTLIFETIME, PLEN, PREFIX, PRF)
    # Give the kernel time to notice our RA
    time.sleep(0.01)
    routes = self.FindRoutesWithGateway()
    self.AssertExpirationInRange(routes, RTLIFETIME, 1)
    self.DelRA6(PREFIX, PLEN)

  def testZeroLengthPrefix(self):
    PREFIX = "2001:db8:8906:2345::"
    RTLIFETIME = self.RA_VALIDITY * 2
    PLEN = 0
    PRF = 0
    # Max plen = 0 still allows default RIOs!
    self.SetAcceptRaRtInfoMaxPlen(PLEN)
    self.SendRA(self.NETID)
    # Give the kernel time to notice our RA
    time.sleep(0.01)
    default = self.FindRoutesWithGateway()
    self.AssertExpirationInRange(default, self.RA_VALIDITY, 1)
    # RIO with prefix length = 0, should overwrite default route lifetime
    # note that the RIO lifetime overwrites the RA lifetime.
    self.SendRIO(RTLIFETIME, PLEN, PREFIX, PRF)
    # Give the kernel time to notice our RA
    time.sleep(0.01)
    default = self.FindRoutesWithGateway()
    self.AssertExpirationInRange(default, RTLIFETIME, 1)
    self.DelRA6(PREFIX, PLEN)

  def testManyRIOs(self):
    RTLIFETIME = 68012
    PLEN = 56
    PRF = 0
    COUNT = 1000
    baseline = self.CountRoutes()
    self.SetAcceptRaRtInfoMaxPlen(56)
    # Send many RIOs compared to the expected number on a healthy system.
    for i in xrange(0, COUNT):
      prefix = "2001:db8:%x:1100::" % i
      self.SendRIO(RTLIFETIME, PLEN, prefix, PRF)
    time.sleep(0.1)
    self.assertEquals(COUNT + baseline, self.CountRoutes())
    for i in xrange(0, COUNT):
      prefix = "2001:db8:%x:1100::" % i
      self.DelRA6(prefix, PLEN)
    # Expect that we can return to baseline config without lingering routes.
    self.assertEquals(baseline, self.CountRoutes())

class RATest(multinetwork_base.MultiNetworkBaseTest):

  def testDoesNotHaveObsoleteSysctl(self):
    self.assertFalse(os.path.isfile(
        "/proc/sys/net/ipv6/route/autoconf_table_offset"))

  @unittest.skipUnless(multinetwork_base.HAVE_AUTOCONF_TABLE,
                       "no support for per-table autoconf")
  def testPurgeDefaultRouters(self):

    def CheckIPv6Connectivity(expect_connectivity):
      for netid in self.NETIDS:
        s = net_test.UDPSocket(AF_INET6)
        self.SetSocketMark(s, netid)
        if expect_connectivity:
          self.assertTrue(s.sendto(UDP_PAYLOAD, (net_test.IPV6_ADDR, 1234)))
        else:
          self.assertRaisesErrno(errno.ENETUNREACH, s.sendto, UDP_PAYLOAD,
                                 (net_test.IPV6_ADDR, 1234))

    try:
      CheckIPv6Connectivity(True)
      self.SetIPv6SysctlOnAllIfaces("accept_ra", 1)
      self.SetSysctl("/proc/sys/net/ipv6/conf/all/forwarding", 1)
      CheckIPv6Connectivity(False)
    finally:
      self.SetSysctl("/proc/sys/net/ipv6/conf/all/forwarding", 0)
      for netid in self.NETIDS:
        self.SendRA(netid)
      CheckIPv6Connectivity(True)

  def testOnlinkCommunication(self):
    """Checks that on-link communication goes direct and not through routers."""
    for netid in self.tuns:
      # Send a UDP packet to a random on-link destination.
      s = net_test.UDPSocket(AF_INET6)
      iface = self.GetInterfaceName(netid)
      self.BindToDevice(s, iface)
      # dstaddr can never be our address because GetRandomDestination only fills
      # in the lower 32 bits, but our address has 0xff in the byte before that
      # (since it's constructed from the EUI-64 and so has ff:fe in the middle).
      dstaddr = self.GetRandomDestination(self.OnlinkPrefix(6, netid))
      s.sendto(UDP_PAYLOAD, (dstaddr, 53))

      # Expect an NS for that destination on the interface.
      myaddr = self.MyAddress(6, netid)
      mymac = self.MyMacAddress(netid)
      desc, expected = packets.NS(myaddr, dstaddr, mymac)
      msg = "Sending UDP packet to on-link destination: expecting %s" % desc
      time.sleep(0.0001)  # Required to make the test work on kernel 3.1(!)
      self.ExpectPacketOn(netid, msg, expected)

      # Send an NA.
      tgtmac = "02:00:00:00:%02x:99" % netid
      _, reply = packets.NA(dstaddr, myaddr, tgtmac)
      # Don't use ReceivePacketOn, since that uses the router's MAC address as
      # the source. Instead, construct our own Ethernet header with source
      # MAC of tgtmac.
      reply = scapy.Ether(src=tgtmac, dst=mymac) / reply
      self.ReceiveEtherPacketOn(netid, reply)

      # Expect the kernel to send the original UDP packet now that the ND cache
      # entry has been populated.
      sport = s.getsockname()[1]
      desc, expected = packets.UDP(6, myaddr, dstaddr, sport=sport)
      msg = "After NA response, expecting %s" % desc
      self.ExpectPacketOn(netid, msg, expected)

  # This test documents a known issue: routing tables are never deleted.
  @unittest.skipUnless(multinetwork_base.HAVE_AUTOCONF_TABLE,
                       "no support for per-table autoconf")
  def testLeftoverRoutes(self):
    def GetNumRoutes():
      return len(open("/proc/net/ipv6_route").readlines())

    num_routes = GetNumRoutes()
    for i in xrange(10, 20):
      try:
        self.tuns[i] = self.CreateTunInterface(i)
        self.SendRA(i)
        self.tuns[i].close()
      finally:
        del self.tuns[i]
    self.assertLess(num_routes, GetNumRoutes())


class PMTUTest(multinetwork_base.InboundMarkingTest):

  PAYLOAD_SIZE = 1400
  dstaddrs = set()

  def GetSocketMTU(self, version, s):
    if version == 6:
      ip6_mtuinfo = s.getsockopt(net_test.SOL_IPV6, csocket.IPV6_PATHMTU, 32)
      unused_sockaddr, mtu = struct.unpack("=28sI", ip6_mtuinfo)
      return mtu
    else:
      return s.getsockopt(net_test.SOL_IP, csocket.IP_MTU)

  def DisableFragmentationAndReportErrors(self, version, s):
    if version == 4:
      s.setsockopt(net_test.SOL_IP, csocket.IP_MTU_DISCOVER,
                   csocket.IP_PMTUDISC_DO)
      s.setsockopt(net_test.SOL_IP, net_test.IP_RECVERR, 1)
    else:
      s.setsockopt(net_test.SOL_IPV6, csocket.IPV6_DONTFRAG, 1)
      s.setsockopt(net_test.SOL_IPV6, net_test.IPV6_RECVERR, 1)

  def CheckPMTU(self, version, use_connect, modes):

    def SendBigPacket(version, s, dstaddr, netid, payload):
      if use_connect:
        s.send(payload)
      else:
        self.SendOnNetid(version, s, dstaddr, 1234, netid, payload, [])

    for netid in self.tuns:
      for mode in modes:
        s = self.BuildSocket(version, net_test.UDPSocket, netid, mode)
        self.DisableFragmentationAndReportErrors(version, s)

        srcaddr = self.MyAddress(version, netid)
        dst_prefix, intermediate = {
            4: ("172.19.", "172.16.9.12"),
            6: ("2001:db8::", "2001:db8::1")
        }[version]

        # Run this test often enough (e.g., in presubmits), and eventually
        # we'll be unlucky enough to pick the same address twice, in which
        # case the test will fail because the kernel will already have seen
        # the lower MTU. Don't do this.
        dstaddr = self.GetRandomDestination(dst_prefix)
        while dstaddr in self.dstaddrs:
          dstaddr = self.GetRandomDestination(dst_prefix)
        self.dstaddrs.add(dstaddr)

        if use_connect:
          s.connect((dstaddr, 1234))

        payload = self.PAYLOAD_SIZE * "a"

        # Send a packet and receive a packet too big.
        SendBigPacket(version, s, dstaddr, netid, payload)
        received = self.ReadAllPacketsOn(netid)
        self.assertEquals(1, len(received),
                          "unexpected packets: %s" % received[1:])
        _, toobig = packets.ICMPPacketTooBig(version, intermediate, srcaddr,
                                             received[0])
        self.ReceivePacketOn(netid, toobig)

        # Check that another send on the same socket returns EMSGSIZE.
        self.assertRaisesErrno(
            errno.EMSGSIZE,
            SendBigPacket, version, s, dstaddr, netid, payload)

        # If this is a connected socket, make sure the socket MTU was set.
        # Note that in IPv4 this only started working in Linux 3.6!
        if use_connect and (version == 6 or net_test.LINUX_VERSION >= (3, 6)):
          self.assertEquals(packets.PTB_MTU, self.GetSocketMTU(version, s))

        s.close()

        # Check that other sockets pick up the PMTU we have been told about by
        # connecting another socket to the same destination and getting its MTU.
        # This new socket can use any method to select its outgoing interface;
        # here we use a mark for simplicity.
        s2 = self.BuildSocket(version, net_test.UDPSocket, netid, "mark")
        s2.connect((dstaddr, 1234))
        self.assertEquals(packets.PTB_MTU, self.GetSocketMTU(version, s2))

        # Also check the MTU reported by ip route get, this time using the oif.
        routes = self.iproute.GetRoutes(dstaddr, self.ifindices[netid], 0, None)
        self.assertTrue(routes)
        route = routes[0]
        rtmsg, attributes = route
        self.assertEquals(iproute.RTN_UNICAST, rtmsg.type)
        metrics = attributes["RTA_METRICS"]
        self.assertEquals(packets.PTB_MTU, metrics["RTAX_MTU"])

  def testIPv4BasicPMTU(self):
    """Tests IPv4 path MTU discovery.

    Relevant kernel commits:
      upstream net-next:
        6a66271 ipv4, fib: pass LOOPBACK_IFINDEX instead of 0 to flowi4_iif

      android-3.10:
        4bc64dd ipv4, fib: pass LOOPBACK_IFINDEX instead of 0 to flowi4_iif
    """

    self.CheckPMTU(4, True, ["mark", "oif"])
    self.CheckPMTU(4, False, ["mark", "oif"])

  def testIPv6BasicPMTU(self):
    self.CheckPMTU(6, True, ["mark", "oif"])
    self.CheckPMTU(6, False, ["mark", "oif"])

  def testIPv4UIDPMTU(self):
    self.CheckPMTU(4, True, ["uid"])
    self.CheckPMTU(4, False, ["uid"])

  def testIPv6UIDPMTU(self):
    self.CheckPMTU(6, True, ["uid"])
    self.CheckPMTU(6, False, ["uid"])

  # Making Path MTU Discovery work on unmarked  sockets requires that mark
  # reflection be enabled. Otherwise the kernel has no way to know what routing
  # table the original packet used, and thus it won't be able to clone the
  # correct route.

  def testIPv4UnmarkedSocketPMTU(self):
    self.SetMarkReflectSysctls(1)
    try:
      self.CheckPMTU(4, False, [None])
    finally:
      self.SetMarkReflectSysctls(0)

  def testIPv6UnmarkedSocketPMTU(self):
    self.SetMarkReflectSysctls(1)
    try:
      self.CheckPMTU(6, False, [None])
    finally:
      self.SetMarkReflectSysctls(0)


class UidRoutingTest(multinetwork_base.MultiNetworkBaseTest):
  """Tests that per-UID routing works properly.

  Relevant kernel commits:
    upstream net-next:
      7d99569460 net: ipv4: Don't crash if passing a null sk to ip_do_redirect.
      d109e61bfe net: ipv4: Don't crash if passing a null sk to ip_rt_update_pmtu.
      35b80733b3 net: core: add missing check for uid_range in rule_exists.
      e2d118a1cb net: inet: Support UID-based routing in IP protocols.
      622ec2c9d5 net: core: add UID to flows, rules, and routes
      86741ec254 net: core: Add a UID field to struct sock.

    android-3.18:
      b004e79504 net: ipv4: Don't crash if passing a null sk to ip_rt_update_pmtu.
      04c0eace81 net: inet: Support UID-based routing in IP protocols.
      18c36d7b71 net: core: add UID to flows, rules, and routes
      80e3440721 net: core: Add a UID field to struct sock.
      fa8cc2c30c Revert "net: core: Support UID-based routing."
      b585141890 Revert "Handle 'sk' being NULL in UID-based routing."
      5115ab7514 Revert "net: core: fix UID-based routing build"
      f9f4281f79 Revert "ANDROID: net: fib: remove duplicate assignment"

    android-4.4:
      341965cf10 net: ipv4: Don't crash if passing a null sk to ip_rt_update_pmtu.
      344afd627c net: inet: Support UID-based routing in IP protocols.
      03441d56d8 net: core: add UID to flows, rules, and routes
      eb964bdba7 net: core: Add a UID field to struct sock.
      9789b697c6 Revert "net: core: Support UID-based routing."
  """

  def GetRulesAtPriority(self, version, priority):
    rules = self.iproute.DumpRules(version)
    out = [(rule, attributes) for rule, attributes in rules
           if attributes.get("FRA_PRIORITY", 0) == priority]
    return out

  def CheckInitialTablesHaveNoUIDs(self, version):
    rules = []
    for priority in [0, 32766, 32767]:
      rules.extend(self.GetRulesAtPriority(version, priority))
    for _, attributes in rules:
      self.assertNotIn("FRA_UID_RANGE", attributes)

  def testIPv4InitialTablesHaveNoUIDs(self):
    self.CheckInitialTablesHaveNoUIDs(4)

  def testIPv6InitialTablesHaveNoUIDs(self):
    self.CheckInitialTablesHaveNoUIDs(6)

  @staticmethod
  def _Random():
    return random.randint(1000000, 2000000)

  def CheckGetAndSetRules(self, version):
    start, end = tuple(sorted([self._Random(), self._Random()]))
    table = self._Random()
    priority = self._Random()

    # Can't create a UID range to UID -1 because -1 is INVALID_UID...
    self.assertRaisesErrno(
        errno.EINVAL,
        self.iproute.UidRangeRule, version, True, 100, 0xffffffff, table,
        priority)

    # ... but -2 is valid.
    self.iproute.UidRangeRule(version, True, 100, 0xfffffffe, table, priority)
    self.iproute.UidRangeRule(version, False, 100, 0xfffffffe, table, priority)

    try:
      # Create a UID range rule.
      self.iproute.UidRangeRule(version, True, start, end, table, priority)

      # Check that deleting the wrong UID range doesn't work.
      self.assertRaisesErrno(
          errno.ENOENT,
          self.iproute.UidRangeRule, version, False, start, end + 1, table,
          priority)
      self.assertRaisesErrno(errno.ENOENT,
        self.iproute.UidRangeRule, version, False, start + 1, end, table,
        priority)

      # Check that the UID range appears in dumps.
      rules = self.GetRulesAtPriority(version, priority)
      self.assertTrue(rules)
      _, attributes = rules[-1]
      self.assertEquals(priority, attributes["FRA_PRIORITY"])
      uidrange = attributes["FRA_UID_RANGE"]
      self.assertEquals(start, uidrange.start)
      self.assertEquals(end, uidrange.end)
      self.assertEquals(table, attributes["FRA_TABLE"])
    finally:
      self.iproute.UidRangeRule(version, False, start, end, table, priority)
      self.assertRaisesErrno(
          errno.ENOENT,
          self.iproute.UidRangeRule, version, False, start, end, table,
          priority)

    fwmask = 0xfefefefe
    try:
      # Create a rule without a UID range.
      self.iproute.FwmarkRule(version, True, 300, fwmask, 301, priority + 1)

      # Check it doesn't have a UID range.
      rules = self.GetRulesAtPriority(version, priority + 1)
      self.assertTrue(rules)
      for _, attributes in rules:
        self.assertIn("FRA_TABLE", attributes)
        self.assertNotIn("FRA_UID_RANGE", attributes)
    finally:
      self.iproute.FwmarkRule(version, False, 300, fwmask, 301, priority + 1)

    # Test that EEXIST worksfor UID range rules too. This behaviour was only
    # added in 4.8.
    if net_test.LINUX_VERSION >= (4, 8, 0):
      ranges = [(100, 101), (100, 102), (99, 101), (1234, 5678)]
      dup = ranges[0]
      try:
        # Check that otherwise identical rules with different UID ranges can be
        # created without EEXIST.
        for start, end in ranges:
          self.iproute.UidRangeRule(version, True, start, end, table, priority)
        # ... but EEXIST is returned if the UID range is identical.
        self.assertRaisesErrno(
          errno.EEXIST,
          self.iproute.UidRangeRule, version, True, dup[0], dup[1], table,
          priority)
      finally:
        # Clean up.
        for start, end in ranges + [dup]:
          try:
            self.iproute.UidRangeRule(version, False, start, end, table,
                                      priority)
          except IOError:
            pass

  def testIPv4GetAndSetRules(self):
    self.CheckGetAndSetRules(4)

  def testIPv6GetAndSetRules(self):
    self.CheckGetAndSetRules(6)

  @unittest.skipUnless(net_test.LINUX_VERSION >= (4, 9, 0), "not backported")
  def testDeleteErrno(self):
    for version in [4, 6]:
      table = self._Random()
      priority = self._Random()
      self.assertRaisesErrno(
          errno.EINVAL,
          self.iproute.UidRangeRule, version, False, 100, 0xffffffff, table,
          priority)

  def ExpectNoRoute(self, addr, oif, mark, uid):
    # The lack of a route may be either an error, or an unreachable route.
    try:
      routes = self.iproute.GetRoutes(addr, oif, mark, uid)
      rtmsg, _ = routes[0]
      self.assertEquals(iproute.RTN_UNREACHABLE, rtmsg.type)
    except IOError, e:
      if int(e.errno) != int(errno.ENETUNREACH):
        raise e

  def ExpectRoute(self, addr, oif, mark, uid):
    routes = self.iproute.GetRoutes(addr, oif, mark, uid)
    rtmsg, _ = routes[0]
    self.assertEquals(iproute.RTN_UNICAST, rtmsg.type)

  def CheckGetRoute(self, version, addr):
    self.ExpectNoRoute(addr, 0, 0, 0)
    for netid in self.NETIDS:
      uid = self.UidForNetid(netid)
      self.ExpectRoute(addr, 0, 0, uid)
    self.ExpectNoRoute(addr, 0, 0, 0)

  def testIPv4RouteGet(self):
    self.CheckGetRoute(4, net_test.IPV4_ADDR)

  def testIPv6RouteGet(self):
    self.CheckGetRoute(6, net_test.IPV6_ADDR)

  def testChangeFdAttributes(self):
    netid = random.choice(self.NETIDS)
    uid = self._Random()
    table = self._TableForNetid(netid)
    remoteaddr = self.GetRemoteAddress(6)
    s = socket(AF_INET6, SOCK_DGRAM, 0)

    def CheckSendFails():
      self.assertRaisesErrno(errno.ENETUNREACH,
                             s.sendto, "foo", (remoteaddr, 53))
    def CheckSendSucceeds():
      self.assertEquals(len("foo"), s.sendto("foo", (remoteaddr, 53)))

    CheckSendFails()
    self.iproute.UidRangeRule(6, True, uid, uid, table, self.PRIORITY_UID)
    try:
      CheckSendFails()
      os.fchown(s.fileno(), uid, -1)
      CheckSendSucceeds()
      os.fchown(s.fileno(), -1, -1)
      CheckSendSucceeds()
      os.fchown(s.fileno(), -1, 12345)
      CheckSendSucceeds()
      os.fchmod(s.fileno(), 0777)
      CheckSendSucceeds()
      os.fchown(s.fileno(), 0, -1)
      CheckSendFails()
    finally:
      self.iproute.UidRangeRule(6, False, uid, uid, table, self.PRIORITY_UID)


class RulesTest(net_test.NetworkTest):

  RULE_PRIORITY = 99999
  FWMASK = 0xffffffff

  def setUp(self):
    self.iproute = iproute.IPRoute()
    for version in [4, 6]:
      self.iproute.DeleteRulesAtPriority(version, self.RULE_PRIORITY)

  def tearDown(self):
    for version in [4, 6]:
      self.iproute.DeleteRulesAtPriority(version, self.RULE_PRIORITY)

  def testRuleDeletionMatchesTable(self):
    for version in [4, 6]:
      # Add rules with mark 300 pointing at tables 301 and 302.
      # This checks for a kernel bug where deletion request for tables > 256
      # ignored the table.
      self.iproute.FwmarkRule(version, True, 300, self.FWMASK, 301,
                              priority=self.RULE_PRIORITY)
      self.iproute.FwmarkRule(version, True, 300, self.FWMASK, 302,
                              priority=self.RULE_PRIORITY)
      # Delete rule with mark 300 pointing at table 302.
      self.iproute.FwmarkRule(version, False, 300, self.FWMASK, 302,
                              priority=self.RULE_PRIORITY)
      # Check that the rule pointing at table 301 is still around.
      attributes = [a for _, a in self.iproute.DumpRules(version)
                    if a.get("FRA_PRIORITY", 0) == self.RULE_PRIORITY]
      self.assertEquals(1, len(attributes))
      self.assertEquals(301, attributes[0]["FRA_TABLE"])


if __name__ == "__main__":
  unittest.main()
