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

# pylint: disable=g-bad-todo

import errno
import os
import posix
import random
from socket import *  # pylint: disable=wildcard-import
import struct
import sys
import threading
import time
import unittest

from scapy import all as scapy

import csocket
import multinetwork_base
import net_test


HAVE_PROC_NET_ICMP6 = os.path.isfile("/proc/net/icmp6")

ICMP_ECHO = 8
ICMP_ECHOREPLY = 0
ICMPV6_ECHO_REQUEST = 128
ICMPV6_ECHO_REPLY = 129
IPV6_MIN_MTU = 1280
ICMPV6_HEADER_LEN = 8
ICMPV6_PKT_TOOBIG = 2


class PingReplyThread(threading.Thread):

  MIN_TTL = 10
  INTERMEDIATE_IPV4 = "192.0.2.2"
  INTERMEDIATE_IPV6 = "2001:db8:1:2::ace:d00d"
  NEIGHBOURS = ["fe80::1"]
  LINK_MTU = 1300

  def __init__(self, tun, mymac, routermac, routeraddr):
    super(PingReplyThread, self).__init__()
    self._tun = tun
    self._started = False
    self._stopped = False
    self._mymac = mymac
    self._routermac = routermac
    self._routeraddr = routeraddr

  def IsStarted(self):
    return self._started

  def Stop(self):
    self._stopped = True

  def ChecksumValid(self, packet):
    # Get and clear the checksums.
    def GetAndClearChecksum(layer):
      if not layer:
        return
      try:
        checksum = layer.chksum
        del layer.chksum
      except AttributeError:
        checksum = layer.cksum
        del layer.cksum
      return checksum

    def GetChecksum(layer):
      try:
        return layer.chksum
      except AttributeError:
        return layer.cksum

    layers = ["IP", "ICMP", scapy.ICMPv6EchoRequest]
    sums = {}
    for name in layers:
      sums[name] = GetAndClearChecksum(packet.getlayer(name))

    # Serialize the packet, so scapy recalculates the checksums, and compare
    # them with the ones in the packet.
    packet = packet.__class__(str(packet))
    for name in layers:
      layer = packet.getlayer(name)
      if layer and GetChecksum(layer) != sums[name]:
        return False

    return True

  def SendTimeExceeded(self, version, packet):
    if version == 4:
      src = packet.getlayer(scapy.IP).src
      self.SendPacket(
          scapy.IP(src=self.INTERMEDIATE_IPV4, dst=src) /
          scapy.ICMP(type=11, code=0) /
          packet)
    elif version == 6:
      src = packet.getlayer(scapy.IPv6).src
      self.SendPacket(
          scapy.IPv6(src=self.INTERMEDIATE_IPV6, dst=src) /
          scapy.ICMPv6TimeExceeded(code=0) /
          packet)

  def SendPacketTooBig(self, packet):
      src = packet.getlayer(scapy.IPv6).src
      datalen = IPV6_MIN_MTU - ICMPV6_HEADER_LEN
      self.SendPacket(
          scapy.IPv6(src=self.INTERMEDIATE_IPV6, dst=src) /
          scapy.ICMPv6PacketTooBig(mtu=self.LINK_MTU) /
          str(packet)[:datalen])

  def IPv4Packet(self, ip):
    icmp = ip.getlayer(scapy.ICMP)

    # We only support ping for now.
    if (ip.proto != IPPROTO_ICMP or
        icmp.type != ICMP_ECHO or
        icmp.code != 0):
      return

    # Check the checksums.
    if not self.ChecksumValid(ip):
      return

    if ip.ttl < self.MIN_TTL:
      self.SendTimeExceeded(4, ip)
      return

    icmp.type = ICMP_ECHOREPLY
    self.SwapAddresses(ip)
    self.SendPacket(ip)

  def IPv6Packet(self, ipv6):
    icmpv6 = ipv6.getlayer(scapy.ICMPv6EchoRequest)

    # We only support ping for now.
    if (ipv6.nh != IPPROTO_ICMPV6 or
        not icmpv6 or
        icmpv6.type != ICMPV6_ECHO_REQUEST or
        icmpv6.code != 0):
      return

    # Check the checksums.
    if not self.ChecksumValid(ipv6):
      return

    if ipv6.dst.startswith("ff02::"):
      ipv6.dst = ipv6.src
      for src in [self._routeraddr]:
        ipv6.src = src
        icmpv6.type = ICMPV6_ECHO_REPLY
        self.SendPacket(ipv6)
    elif ipv6.hlim < self.MIN_TTL:
      self.SendTimeExceeded(6, ipv6)
    elif ipv6.plen > self.LINK_MTU:
      self.SendPacketTooBig(ipv6)
    else:
      icmpv6.type = ICMPV6_ECHO_REPLY
      if ipv6.dst.startswith("fe80:") and ipv6.dst != self._routeraddr:
        return
      self.SwapAddresses(ipv6)
      self.SendPacket(ipv6)

  def SwapAddresses(self, packet):
    src = packet.src
    packet.src = packet.dst
    packet.dst = src

  def SendPacket(self, packet):
    packet = scapy.Ether(src=self._routermac, dst=self._mymac) / packet
    try:
      posix.write(self._tun.fileno(), str(packet))
    except Exception, e:
      if not self._stopped:
        raise e

  def run(self):
    self._started = True
    while not self._stopped:
      try:
        packet = posix.read(self._tun.fileno(), 4096)
      except OSError, e:
        if e.errno == errno.EAGAIN:
          continue
        else:
          break
      except ValueError, e:
        if not self._stopped:
          raise e

      ether = scapy.Ether(packet)
      if ether.type == net_test.ETH_P_IPV6:
        self.IPv6Packet(ether.payload)
      elif ether.type == net_test.ETH_P_IP:
        self.IPv4Packet(ether.payload)


class Ping6Test(multinetwork_base.MultiNetworkBaseTest):

  @classmethod
  def WaitForReplyThreads(cls):
    # Wait 2s for the reply threads to start. If they don't, don't blow up, as
    # that would cause tearDownClass not to be called and thus not clean up
    # routing configuration, breaking subsequent tests. Instead, just let these
    # tests fail.
    _INTERVAL = 0.1
    _ATTEMPTS = 20
    for i in xrange(0, _ATTEMPTS):
      for netid in cls.NETIDS:
        if all(thread.IsStarted() for thread in cls.reply_threads.values()):
          return
        time.sleep(_INTERVAL)
    msg = "WARNING: reply threads not all started after %.1f seconds\n" % (
        _ATTEMPTS * _INTERVAL)
    sys.stderr.write(msg)

  @classmethod
  def StopReplyThreads(cls):
    for thread in cls.reply_threads.values():
      thread.Stop()

  @classmethod
  def setUpClass(cls):
    super(Ping6Test, cls).setUpClass()
    cls.reply_threads = {}
    for netid in cls.NETIDS:
      cls.reply_threads[netid] = PingReplyThread(
        cls.tuns[netid],
        cls.MyMacAddress(netid),
        cls.RouterMacAddress(netid),
        cls._RouterAddress(netid, 6))
      cls.reply_threads[netid].start()
    cls.WaitForReplyThreads()
    cls.netid = random.choice(cls.NETIDS)
    cls.SetDefaultNetwork(cls.netid)

  @classmethod
  def tearDownClass(cls):
    cls.StopReplyThreads()
    cls.ClearDefaultNetwork()
    super(Ping6Test, cls).tearDownClass()

  def setUp(self):
    self.ifname = self.GetInterfaceName(self.netid)
    self.ifindex = self.ifindices[self.netid]
    self.lladdr = net_test.GetLinkAddress(self.ifname, True)
    self.globaladdr = net_test.GetLinkAddress(self.ifname, False)

  def assertValidPingResponse(self, s, data):
    family = s.family

    # Receive the reply.
    rcvd, src = s.recvfrom(32768)
    self.assertNotEqual(0, len(rcvd), "No data received")

    # If this is a dual-stack socket sending to a mapped IPv4 address, treat it
    # as IPv4.
    if src[0].startswith("::ffff:"):
      family = AF_INET
      src = (src[0].replace("::ffff:", ""), src[1:])

    # Check the data being sent is valid.
    self.assertGreater(len(data), 7, "Not enough data for ping packet")
    if family == AF_INET:
      self.assertTrue(data.startswith("\x08\x00"), "Not an IPv4 echo request")
    elif family == AF_INET6:
      self.assertTrue(data.startswith("\x80\x00"), "Not an IPv6 echo request")
    else:
      self.fail("Unknown socket address family %d" * s.family)

    # Check address, ICMP type, and ICMP code.
    if family == AF_INET:
      addr, unused_port = src
      self.assertGreaterEqual(len(addr), len("1.1.1.1"))
      self.assertTrue(rcvd.startswith("\x00\x00"), "Not an IPv4 echo reply")
    else:
      addr, unused_port, flowlabel, scope_id = src  # pylint: disable=unbalanced-tuple-unpacking
      self.assertGreaterEqual(len(addr), len("::"))
      self.assertTrue(rcvd.startswith("\x81\x00"), "Not an IPv6 echo reply")
      # Check that the flow label is zero and that the scope ID is sane.
      self.assertEqual(flowlabel, 0)
      if addr.startswith("fe80::"):
        self.assertTrue(scope_id in self.ifindices.values())
      else:
        self.assertEquals(0, scope_id)

    # TODO: check the checksum. We can't do this easily now for ICMPv6 because
    # we don't have the IP addresses so we can't construct the pseudoheader.

    # Check the sequence number and the data.
    self.assertEqual(len(data), len(rcvd))
    self.assertEqual(data[6:].encode("hex"), rcvd[6:].encode("hex"))

  @staticmethod
  def IsAlmostEqual(expected, actual, delta):
    return abs(expected - actual) < delta

  def CheckSockStatFile(self, name, srcaddr, srcport, dstaddr, dstport, state,
                        txmem=0, rxmem=0):
    expected = ["%s:%04X" % (net_test.FormatSockStatAddress(srcaddr), srcport),
                "%s:%04X" % (net_test.FormatSockStatAddress(dstaddr), dstport),
                "%02X" % state,
                "%08X:%08X" % (txmem, rxmem),
                str(os.getuid()), "2", "0"]
    for actual in self.ReadProcNetSocket(name):
      # Check that rxmem and txmem don't differ too much from each other.
      actual_txmem, actual_rxmem = expected[3].split(":")
      if self.IsAlmostEqual(txmem, int(actual_txmem, 16), txmem / 4):
        return
      if self.IsAlmostEqual(rxmem, int(actual_rxmem, 16), rxmem / 4):
        return

      # Check all the parameters except rxmem and txmem.
      expected[3] = actual[3]
      if expected == actual:
        return

    self.fail("Cound not find socket matching %s" % expected)

  def testIPv4SendWithNoConnection(self):
    s = net_test.IPv4PingSocket()
    self.assertRaisesErrno(errno.EDESTADDRREQ, s.send, net_test.IPV4_PING)

  def testIPv6SendWithNoConnection(self):
    s = net_test.IPv6PingSocket()
    self.assertRaisesErrno(errno.EDESTADDRREQ, s.send, net_test.IPV6_PING)

  def testIPv4LoopbackPingWithConnect(self):
    s = net_test.IPv4PingSocket()
    s.connect(("127.0.0.1", 55))
    data = net_test.IPV4_PING + "foobarbaz"
    s.send(data)
    self.assertValidPingResponse(s, data)

  def testIPv6LoopbackPingWithConnect(self):
    s = net_test.IPv6PingSocket()
    s.connect(("::1", 55))
    s.send(net_test.IPV6_PING)
    self.assertValidPingResponse(s, net_test.IPV6_PING)

  def testIPv4PingUsingSendto(self):
    s = net_test.IPv4PingSocket()
    written = s.sendto(net_test.IPV4_PING, (net_test.IPV4_ADDR, 55))
    self.assertEquals(len(net_test.IPV4_PING), written)
    self.assertValidPingResponse(s, net_test.IPV4_PING)

  def testIPv6PingUsingSendto(self):
    s = net_test.IPv6PingSocket()
    written = s.sendto(net_test.IPV6_PING, (net_test.IPV6_ADDR, 55))
    self.assertEquals(len(net_test.IPV6_PING), written)
    self.assertValidPingResponse(s, net_test.IPV6_PING)

  def testIPv4NoCrash(self):
    # Python 2.x does not provide either read() or recvmsg.
    s = net_test.IPv4PingSocket()
    written = s.sendto(net_test.IPV4_PING, ("127.0.0.1", 55))
    self.assertEquals(len(net_test.IPV4_PING), written)
    fd = s.fileno()
    reply = posix.read(fd, 4096)
    self.assertEquals(written, len(reply))

  def testIPv6NoCrash(self):
    # Python 2.x does not provide either read() or recvmsg.
    s = net_test.IPv6PingSocket()
    written = s.sendto(net_test.IPV6_PING, ("::1", 55))
    self.assertEquals(len(net_test.IPV6_PING), written)
    fd = s.fileno()
    reply = posix.read(fd, 4096)
    self.assertEquals(written, len(reply))

  def testCrossProtocolCrash(self):
    # Checks that an ICMP error containing a ping packet that matches the ID
    # of a socket of the wrong protocol (which can happen when using 464xlat)
    # doesn't crash the kernel.

    # We can only test this using IPv6 unreachables and IPv4 ping sockets,
    # because IPv4 packets sent by scapy.send() on loopback are not received by
    # the kernel. So we don't actually use this function yet.
    def GetIPv4Unreachable(port):  # pylint: disable=unused-variable
      return (scapy.IP(src="192.0.2.1", dst="127.0.0.1") /
              scapy.ICMP(type=3, code=0) /
              scapy.IP(src="127.0.0.1", dst="127.0.0.1") /
              scapy.ICMP(type=8, id=port, seq=1))

    def GetIPv6Unreachable(port):
      return (scapy.IPv6(src="::1", dst="::1") /
              scapy.ICMPv6DestUnreach() /
              scapy.IPv6(src="::1", dst="::1") /
              scapy.ICMPv6EchoRequest(id=port, seq=1, data="foobarbaz"))

    # An unreachable matching the ID of a socket of the wrong protocol
    # shouldn't crash.
    s = net_test.IPv4PingSocket()
    s.connect(("127.0.0.1", 12345))
    _, port = s.getsockname()
    scapy.send(GetIPv6Unreachable(port), verbose=False)
    # No crash? Good.

  def testCrossProtocolCalls(self):
    """Tests that passing in the wrong family returns EAFNOSUPPORT.

    Relevant kernel commits:
      upstream net:
        91a0b60 net/ping: handle protocol mismatching scenario
        9145736d net: ping: Return EAFNOSUPPORT when appropriate.

      android-3.10:
        78a6809 net/ping: handle protocol mismatching scenario
        428e6d6 net: ping: Return EAFNOSUPPORT when appropriate.
    """

    def CheckEAFNoSupport(function, *args):
      self.assertRaisesErrno(errno.EAFNOSUPPORT, function, *args)

    ipv6sockaddr = csocket.Sockaddr((net_test.IPV6_ADDR, 53))

    # In order to check that IPv6 socket calls return EAFNOSUPPORT when passed
    # IPv4 socket address structures, we need to pass down a socket address
    # length argument that's at least sizeof(sockaddr_in6). Otherwise, the calls
    # will fail immediately with EINVAL because the passed-in socket length is
    # too short. So create a sockaddr_in that's as long as a sockaddr_in6.
    ipv4sockaddr = csocket.Sockaddr((net_test.IPV4_ADDR, 53))
    ipv4sockaddr = csocket.SockaddrIn6(
        ipv4sockaddr.Pack() +
        "\x00" * (len(csocket.SockaddrIn6) - len(csocket.SockaddrIn)))

    s4 = net_test.IPv4PingSocket()
    s6 = net_test.IPv6PingSocket()

    # We can't just call s.connect(), s.bind() etc. with a tuple of the wrong
    # address family, because the Python implementation will just pass garbage
    # down to the kernel. So call the C functions directly.
    CheckEAFNoSupport(csocket.Bind, s4, ipv6sockaddr)
    CheckEAFNoSupport(csocket.Bind, s6, ipv4sockaddr)
    CheckEAFNoSupport(csocket.Connect, s4, ipv6sockaddr)
    CheckEAFNoSupport(csocket.Connect, s6, ipv4sockaddr)
    CheckEAFNoSupport(csocket.Sendmsg,
                      s4, ipv6sockaddr, net_test.IPV4_PING, None, 0)
    CheckEAFNoSupport(csocket.Sendmsg,
                      s6, ipv4sockaddr, net_test.IPV6_PING, None, 0)

  def testIPv4Bind(self):
    # Bind to unspecified address.
    s = net_test.IPv4PingSocket()
    s.bind(("0.0.0.0", 544))
    self.assertEquals(("0.0.0.0", 544), s.getsockname())

    # Bind to loopback.
    s = net_test.IPv4PingSocket()
    s.bind(("127.0.0.1", 99))
    self.assertEquals(("127.0.0.1", 99), s.getsockname())

    # Binding twice is not allowed.
    self.assertRaisesErrno(errno.EINVAL, s.bind, ("127.0.0.1", 22))

    # But binding two different sockets to the same ID is allowed.
    s2 = net_test.IPv4PingSocket()
    s2.bind(("127.0.0.1", 99))
    self.assertEquals(("127.0.0.1", 99), s2.getsockname())
    s3 = net_test.IPv4PingSocket()
    s3.bind(("127.0.0.1", 99))
    self.assertEquals(("127.0.0.1", 99), s3.getsockname())

    # If two sockets bind to the same port, the first one to call read() gets
    # the response.
    s4 = net_test.IPv4PingSocket()
    s5 = net_test.IPv4PingSocket()
    s4.bind(("0.0.0.0", 167))
    s5.bind(("0.0.0.0", 167))
    s4.sendto(net_test.IPV4_PING, (net_test.IPV4_ADDR, 44))
    self.assertValidPingResponse(s5, net_test.IPV4_PING)
    csocket.SetSocketTimeout(s4, 100)
    self.assertRaisesErrno(errno.EAGAIN, s4.recv, 32768)

    # If SO_REUSEADDR is turned off, then we get EADDRINUSE.
    s6 = net_test.IPv4PingSocket()
    s4.setsockopt(SOL_SOCKET, SO_REUSEADDR, 0)
    self.assertRaisesErrno(errno.EADDRINUSE, s6.bind, ("0.0.0.0", 167))

    # Can't bind after sendto.
    s = net_test.IPv4PingSocket()
    s.sendto(net_test.IPV4_PING, (net_test.IPV4_ADDR, 9132))
    self.assertRaisesErrno(errno.EINVAL, s.bind, ("0.0.0.0", 5429))

  def testIPv6Bind(self):
    # Bind to unspecified address.
    s = net_test.IPv6PingSocket()
    s.bind(("::", 769))
    self.assertEquals(("::", 769, 0, 0), s.getsockname())

    # Bind to loopback.
    s = net_test.IPv6PingSocket()
    s.bind(("::1", 99))
    self.assertEquals(("::1", 99, 0, 0), s.getsockname())

    # Binding twice is not allowed.
    self.assertRaisesErrno(errno.EINVAL, s.bind, ("::1", 22))

    # But binding two different sockets to the same ID is allowed.
    s2 = net_test.IPv6PingSocket()
    s2.bind(("::1", 99))
    self.assertEquals(("::1", 99, 0, 0), s2.getsockname())
    s3 = net_test.IPv6PingSocket()
    s3.bind(("::1", 99))
    self.assertEquals(("::1", 99, 0, 0), s3.getsockname())

    # Binding both IPv4 and IPv6 to the same socket works.
    s4 = net_test.IPv4PingSocket()
    s6 = net_test.IPv6PingSocket()
    s4.bind(("0.0.0.0", 444))
    s6.bind(("::", 666, 0, 0))

    # Can't bind after sendto.
    s = net_test.IPv6PingSocket()
    s.sendto(net_test.IPV6_PING, (net_test.IPV6_ADDR, 9132))
    self.assertRaisesErrno(errno.EINVAL, s.bind, ("::", 5429))

  def testIPv4InvalidBind(self):
    s = net_test.IPv4PingSocket()
    self.assertRaisesErrno(errno.EADDRNOTAVAIL,
                           s.bind, ("255.255.255.255", 1026))
    self.assertRaisesErrno(errno.EADDRNOTAVAIL,
                           s.bind, ("224.0.0.1", 651))
    # Binding to an address we don't have only works with IP_TRANSPARENT.
    self.assertRaisesErrno(errno.EADDRNOTAVAIL,
                           s.bind, (net_test.IPV4_ADDR, 651))
    try:
      s.setsockopt(SOL_IP, net_test.IP_TRANSPARENT, 1)
      s.bind((net_test.IPV4_ADDR, 651))
    except IOError, e:
      if e.errno == errno.EACCES:
        pass  # We're not root. let it go for now.

  def testIPv6InvalidBind(self):
    s = net_test.IPv6PingSocket()
    self.assertRaisesErrno(errno.EINVAL,
                           s.bind, ("ff02::2", 1026))

    # Binding to an address we don't have only works with IPV6_TRANSPARENT.
    self.assertRaisesErrno(errno.EADDRNOTAVAIL,
                           s.bind, (net_test.IPV6_ADDR, 651))
    try:
      s.setsockopt(net_test.SOL_IPV6, net_test.IPV6_TRANSPARENT, 1)
      s.bind((net_test.IPV6_ADDR, 651))
    except IOError, e:
      if e.errno == errno.EACCES:
        pass  # We're not root. let it go for now.

  def testAfUnspecBind(self):
    # Binding to AF_UNSPEC is treated as IPv4 if the address is 0.0.0.0.
    s4 = net_test.IPv4PingSocket()
    sockaddr = csocket.Sockaddr(("0.0.0.0", 12996))
    sockaddr.family = AF_UNSPEC
    csocket.Bind(s4, sockaddr)
    self.assertEquals(("0.0.0.0", 12996), s4.getsockname())

    # But not if the address is anything else.
    sockaddr = csocket.Sockaddr(("127.0.0.1", 58234))
    sockaddr.family = AF_UNSPEC
    self.assertRaisesErrno(errno.EAFNOSUPPORT, csocket.Bind, s4, sockaddr)

    # This doesn't work for IPv6.
    s6 = net_test.IPv6PingSocket()
    sockaddr = csocket.Sockaddr(("::1", 58997))
    sockaddr.family = AF_UNSPEC
    self.assertRaisesErrno(errno.EAFNOSUPPORT, csocket.Bind, s6, sockaddr)

  def testIPv6ScopedBind(self):
    # Can't bind to a link-local address without a scope ID.
    s = net_test.IPv6PingSocket()
    self.assertRaisesErrno(errno.EINVAL,
                           s.bind, (self.lladdr, 1026, 0, 0))

    # Binding to a link-local address with a scope ID works, and the scope ID is
    # returned by a subsequent getsockname. Interestingly, Python's getsockname
    # returns "fe80:1%foo", even though it does not understand it.
    expected = self.lladdr + "%" + self.ifname
    s.bind((self.lladdr, 4646, 0, self.ifindex))
    self.assertEquals((expected, 4646, 0, self.ifindex), s.getsockname())

    # Of course, for the above to work the address actually has to be configured
    # on the machine.
    self.assertRaisesErrno(errno.EADDRNOTAVAIL,
                           s.bind, ("fe80::f00", 1026, 0, 1))

    # Scope IDs on non-link-local addresses are silently ignored.
    s = net_test.IPv6PingSocket()
    s.bind(("::1", 1234, 0, 1))
    self.assertEquals(("::1", 1234, 0, 0), s.getsockname())

  def testBindAffectsIdentifier(self):
    s = net_test.IPv6PingSocket()
    s.bind((self.globaladdr, 0xf976))
    s.sendto(net_test.IPV6_PING, (net_test.IPV6_ADDR, 55))
    self.assertEquals("\xf9\x76", s.recv(32768)[4:6])

    s = net_test.IPv6PingSocket()
    s.bind((self.globaladdr, 0xace))
    s.sendto(net_test.IPV6_PING, (net_test.IPV6_ADDR, 55))
    self.assertEquals("\x0a\xce", s.recv(32768)[4:6])

  def testLinkLocalAddress(self):
    s = net_test.IPv6PingSocket()
    # Sending to a link-local address with no scope fails with EINVAL.
    self.assertRaisesErrno(errno.EINVAL,
                           s.sendto, net_test.IPV6_PING, ("fe80::1", 55))
    # Sending to link-local address with a scope succeeds. Note that Python
    # doesn't understand the "fe80::1%lo" format, even though it returns it.
    s.sendto(net_test.IPV6_PING, ("fe80::1", 55, 0, self.ifindex))
    # No exceptions? Good.

  def testLinkLocalOif(self):
    """Checks that ping to link-local addresses works correctly.

    Relevant kernel commits:
      upstream net:
        5e45789 net: ipv6: Fix ping to link-local addresses.
    """
    for mode in ["oif", "ucast_oif", None]:
      s = net_test.IPv6PingSocket()
      for netid in self.NETIDS:
        s2 = net_test.IPv6PingSocket()
        dst = self._RouterAddress(netid, 6)
        self.assertTrue(dst.startswith("fe80:"))

        if mode:
          self.SelectInterface(s, netid, mode)
          self.SelectInterface(s2, netid, mode)
          scopeid = 0
        else:
          scopeid = self.ifindices[netid]

        if mode == "oif":
          # If SO_BINDTODEVICE has been set, any attempt to send on another
          # interface returns EINVAL.
          othernetid = self.NETIDS[(self.NETIDS.index(netid) + 1)
                                   % len(self.NETIDS)]
          otherscopeid = self.ifindices[othernetid]
          self.assertRaisesErrno(
              errno.EINVAL,
              s.sendto, net_test.IPV6_PING, (dst, 55, 0, otherscopeid))
          self.assertRaisesErrno(
              errno.EINVAL,
              s.connect, (dst, 55, 0, otherscopeid))

        # Try using both sendto and connect/send.
        # If we get a reply, we sent the packet out on the right interface.
        s.sendto(net_test.IPV6_PING, (dst, 123, 0, scopeid))
        self.assertValidPingResponse(s, net_test.IPV6_PING)

        # IPV6_UNICAST_IF doesn't work on connected sockets.
        if mode != "ucast_oif":
          s2.connect((dst, 123, 0, scopeid))
          s2.send(net_test.IPV6_PING)
          self.assertValidPingResponse(s2, net_test.IPV6_PING)

  def testMappedAddressFails(self):
    s = net_test.IPv6PingSocket()
    s.sendto(net_test.IPV6_PING, (net_test.IPV6_ADDR, 55))
    self.assertValidPingResponse(s, net_test.IPV6_PING)
    s.sendto(net_test.IPV6_PING, ("2001:4860:4860::8844", 55))
    self.assertValidPingResponse(s, net_test.IPV6_PING)
    self.assertRaisesErrno(errno.EINVAL, s.sendto, net_test.IPV6_PING,
                           ("::ffff:192.0.2.1", 55))

  @unittest.skipUnless(False, "skipping: does not work yet")
  def testFlowLabel(self):
    s = net_test.IPv6PingSocket()

    # Specifying a flowlabel without having set IPV6_FLOWINFO_SEND succeeds but
    # the flow label in the packet is not set.
    s.sendto(net_test.IPV6_PING, (net_test.IPV6_ADDR, 93, 0xdead, 0))
    self.assertValidPingResponse(s, net_test.IPV6_PING)  # Checks flow label==0.

    # If IPV6_FLOWINFO_SEND is set on the socket, attempting to set a flow label
    # that is not registered with the flow manager should return EINVAL...
    s.setsockopt(net_test.SOL_IPV6, net_test.IPV6_FLOWINFO_SEND, 1)
    # ... but this doesn't work yet.
    if False:
      self.assertRaisesErrno(errno.EINVAL, s.sendto, net_test.IPV6_PING,
                             (net_test.IPV6_ADDR, 93, 0xdead, 0))

    # After registering the flow label, it gets sent properly, appears in the
    # output packet, and is returned in the response.
    net_test.SetFlowLabel(s, net_test.IPV6_ADDR, 0xdead)
    self.assertEqual(1, s.getsockopt(net_test.SOL_IPV6,
                                     net_test.IPV6_FLOWINFO_SEND))
    s.sendto(net_test.IPV6_PING, (net_test.IPV6_ADDR, 93, 0xdead, 0))
    _, src = s.recvfrom(32768)
    _, _, flowlabel, _ = src
    self.assertEqual(0xdead, flowlabel & 0xfffff)

  def testIPv4Error(self):
    s = net_test.IPv4PingSocket()
    s.setsockopt(SOL_IP, IP_TTL, 2)
    s.setsockopt(SOL_IP, net_test.IP_RECVERR, 1)
    s.sendto(net_test.IPV4_PING, (net_test.IPV4_ADDR, 55))
    # We can't check the actual error because Python 2.7 doesn't implement
    # recvmsg, but we can at least check that the socket returns an error.
    self.assertRaisesErrno(errno.EHOSTUNREACH, s.recv, 32768)  # No response.

  def testIPv6Error(self):
    s = net_test.IPv6PingSocket()
    s.setsockopt(net_test.SOL_IPV6, IPV6_UNICAST_HOPS, 2)
    s.setsockopt(net_test.SOL_IPV6, net_test.IPV6_RECVERR, 1)
    s.sendto(net_test.IPV6_PING, (net_test.IPV6_ADDR, 55))
    # We can't check the actual error because Python 2.7 doesn't implement
    # recvmsg, but we can at least check that the socket returns an error.
    self.assertRaisesErrno(errno.EHOSTUNREACH, s.recv, 32768)  # No response.

  def testIPv6MulticastPing(self):
    s = net_test.IPv6PingSocket()
    # Send a multicast ping and check we get at least one duplicate.
    # The setsockopt should not be necessary, but ping_v6_sendmsg has a bug.
    s.setsockopt(net_test.SOL_IPV6, net_test.IPV6_MULTICAST_IF, self.ifindex)
    s.sendto(net_test.IPV6_PING, ("ff02::1", 55, 0, self.ifindex))
    self.assertValidPingResponse(s, net_test.IPV6_PING)
    self.assertValidPingResponse(s, net_test.IPV6_PING)

  def testIPv4LargePacket(self):
    s = net_test.IPv4PingSocket()
    data = net_test.IPV4_PING + 20000 * "a"
    s.sendto(data, ("127.0.0.1", 987))
    self.assertValidPingResponse(s, data)

  def testIPv6LargePacket(self):
    s = net_test.IPv6PingSocket()
    s.bind(("::", 0xace))
    data = net_test.IPV6_PING + "\x01" + 19994 * "\x00" + "aaaaa"
    s.sendto(data, ("::1", 953))

  @unittest.skipUnless(HAVE_PROC_NET_ICMP6, "skipping: no /proc/net/icmp6")
  def testIcmpSocketsNotInIcmp6(self):
    numrows = len(self.ReadProcNetSocket("icmp"))
    numrows6 = len(self.ReadProcNetSocket("icmp6"))
    s = net_test.Socket(AF_INET, SOCK_DGRAM, IPPROTO_ICMP)
    s.bind(("127.0.0.1", 0xace))
    s.connect(("127.0.0.1", 0xbeef))
    self.assertEquals(numrows + 1, len(self.ReadProcNetSocket("icmp")))
    self.assertEquals(numrows6, len(self.ReadProcNetSocket("icmp6")))

  @unittest.skipUnless(HAVE_PROC_NET_ICMP6, "skipping: no /proc/net/icmp6")
  def testIcmp6SocketsNotInIcmp(self):
    numrows = len(self.ReadProcNetSocket("icmp"))
    numrows6 = len(self.ReadProcNetSocket("icmp6"))
    s = net_test.IPv6PingSocket()
    s.bind(("::1", 0xace))
    s.connect(("::1", 0xbeef))
    self.assertEquals(numrows, len(self.ReadProcNetSocket("icmp")))
    self.assertEquals(numrows6 + 1, len(self.ReadProcNetSocket("icmp6")))

  def testProcNetIcmp(self):
    s = net_test.Socket(AF_INET, SOCK_DGRAM, IPPROTO_ICMP)
    s.bind(("127.0.0.1", 0xace))
    s.connect(("127.0.0.1", 0xbeef))
    self.CheckSockStatFile("icmp", "127.0.0.1", 0xace, "127.0.0.1", 0xbeef, 1)

  @unittest.skipUnless(HAVE_PROC_NET_ICMP6, "skipping: no /proc/net/icmp6")
  def testProcNetIcmp6(self):
    numrows6 = len(self.ReadProcNetSocket("icmp6"))
    s = net_test.IPv6PingSocket()
    s.bind(("::1", 0xace))
    s.connect(("::1", 0xbeef))
    self.CheckSockStatFile("icmp6", "::1", 0xace, "::1", 0xbeef, 1)

    # Check the row goes away when the socket is closed.
    s.close()
    self.assertEquals(numrows6, len(self.ReadProcNetSocket("icmp6")))

    # Try send, bind and connect to check the addresses and the state.
    s = net_test.IPv6PingSocket()
    self.assertEqual(0, len(self.ReadProcNetSocket("icmp6")))
    s.sendto(net_test.IPV6_PING, (net_test.IPV6_ADDR, 12345))
    self.assertEqual(1, len(self.ReadProcNetSocket("icmp6")))

    # Can't bind after sendto, apparently.
    s = net_test.IPv6PingSocket()
    self.assertEqual(0, len(self.ReadProcNetSocket("icmp6")))
    s.bind((self.lladdr, 0xd00d, 0, self.ifindex))
    self.CheckSockStatFile("icmp6", self.lladdr, 0xd00d, "::", 0, 7)

    # Check receive bytes.
    s.setsockopt(net_test.SOL_IPV6, net_test.IPV6_MULTICAST_IF, self.ifindex)
    s.connect(("ff02::1", 0xdead))
    self.CheckSockStatFile("icmp6", self.lladdr, 0xd00d, "ff02::1", 0xdead, 1)
    s.send(net_test.IPV6_PING)
    s.recvfrom(32768, MSG_PEEK)  # Wait until the receive thread replies.
    self.CheckSockStatFile("icmp6", self.lladdr, 0xd00d, "ff02::1", 0xdead, 1,
                           txmem=0, rxmem=0x300)
    self.assertValidPingResponse(s, net_test.IPV6_PING)
    self.CheckSockStatFile("icmp6", self.lladdr, 0xd00d, "ff02::1", 0xdead, 1,
                           txmem=0, rxmem=0)

  def testProcNetUdp6(self):
    s = net_test.Socket(AF_INET6, SOCK_DGRAM, IPPROTO_UDP)
    s.bind(("::1", 0xace))
    s.connect(("::1", 0xbeef))
    self.CheckSockStatFile("udp6", "::1", 0xace, "::1", 0xbeef, 1)

  def testProcNetRaw6(self):
    s = net_test.Socket(AF_INET6, SOCK_RAW, IPPROTO_RAW)
    s.bind(("::1", 0xace))
    s.connect(("::1", 0xbeef))
    self.CheckSockStatFile("raw6", "::1", 0xff, "::1", 0, 1)

  def testIPv6MTU(self):
    """Tests IPV6_RECVERR and path MTU discovery on ping sockets.

    Relevant kernel commits:
      upstream net-next:
        dcb94b8 ipv6: fix endianness error in icmpv6_err
    """
    s = net_test.IPv6PingSocket()
    s.setsockopt(net_test.SOL_IPV6, csocket.IPV6_DONTFRAG, 1)
    s.setsockopt(net_test.SOL_IPV6, csocket.IPV6_MTU_DISCOVER, 2)
    s.setsockopt(net_test.SOL_IPV6, net_test.IPV6_RECVERR, 1)
    s.connect((net_test.IPV6_ADDR, 55))
    pkt = net_test.IPV6_PING + (PingReplyThread.LINK_MTU + 100) * "a"
    s.send(pkt)
    self.assertRaisesErrno(errno.EMSGSIZE, s.recv, 32768)
    data, addr, cmsg = csocket.Recvmsg(s, 4096, 1024, csocket.MSG_ERRQUEUE)

    # Compare the offending packet with the one we sent. To do this we need to
    # calculate the ident of the packet we sent and blank out the checksum of
    # the one we received.
    ident = struct.pack("!H", s.getsockname()[1])
    pkt = pkt[:4] + ident + pkt[6:]
    data = data[:2] + "\x00\x00" + pkt[4:]
    self.assertEquals(pkt, data)

    # Check the address that the packet was sent to.
    # ... except in 4.1, where it just returns an AF_UNSPEC, like this:
    # recvmsg(9, {msg_name(0)={sa_family=AF_UNSPEC,
    #     sa_data="\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"},
    #     msg_iov(1)=[{"\x80\x00\x04\x6b\x00\xc4\x00\x03\x61\x61\x61\x61\x61\x61"..., 4096}],
    #     msg_controllen=64, {cmsg_len=60, cmsg_level=SOL_IPV6, cmsg_type=, ...},
    #     msg_flags=MSG_ERRQUEUE}, MSG_ERRQUEUE) = 1232
    if net_test.LINUX_VERSION != (4, 1, 0):
      self.assertEquals(csocket.Sockaddr(("2001:4860:4860::8888", 0)), addr)

    # Check the cmsg data, including the link MTU.
    mtu = PingReplyThread.LINK_MTU
    src = self.reply_threads[self.netid].INTERMEDIATE_IPV6
    msglist = [
        (net_test.SOL_IPV6, net_test.IPV6_RECVERR,
         (csocket.SockExtendedErr((errno.EMSGSIZE, csocket.SO_ORIGIN_ICMP6,
                                   ICMPV6_PKT_TOOBIG, 0, mtu, 0)),
          csocket.Sockaddr((src, 0))))
    ]

    # IP[V6]_RECVERR in 3.10 appears to return incorrect data for the port.
    # The fix might have been in 676d236, but we don't have that in 3.10 and it
    # touches code all over the tree. Instead, just don't check the port.
    if net_test.LINUX_VERSION <= (3, 14, 0):
      msglist[0][2][1].port = cmsg[0][2][1].port

    self.assertEquals(msglist, cmsg)


if __name__ == "__main__":
  unittest.main()
