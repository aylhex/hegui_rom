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

# pylint: disable=g-bad-todo,g-bad-file-header,wildcard-import
from errno import *  # pylint: disable=wildcard-import
import os
import random
import select
from socket import *  # pylint: disable=wildcard-import
import struct
import threading
import time
import unittest

import cstruct
import multinetwork_base
import net_test
import packets
import sock_diag
import tcp_test

# Mostly empty structure definition containing only the fields we currently use.
TcpInfo = cstruct.Struct("TcpInfo", "64xI", "tcpi_rcv_ssthresh")

NUM_SOCKETS = 30
NO_BYTECODE = ""
LINUX_4_9_OR_ABOVE = net_test.LINUX_VERSION >= (4, 9, 0)
LINUX_4_19_OR_ABOVE = net_test.LINUX_VERSION >= (4, 19, 0)

IPPROTO_SCTP = 132

def HaveUdpDiag():
  """Checks if the current kernel has config CONFIG_INET_UDP_DIAG enabled.

  This config is required for device running 4.9 kernel that ship with P, In
  this case always assume the config is there and use the tests to check if the
  config is enabled as required.

  For all ther other kernel version, there is no way to tell whether a dump
  succeeded: if the appropriate handler wasn't found, __inet_diag_dump just
  returns an empty result instead of an error. So, just check to see if a UDP
  dump returns no sockets when we know it should return one. If not, some tests
  will be skipped.

  Returns:
    True if the kernel is 4.9 or above, or the CONFIG_INET_UDP_DIAG is enabled.
    False otherwise.
  """
  if LINUX_4_9_OR_ABOVE:
      return True;
  s = socket(AF_INET6, SOCK_DGRAM, 0)
  s.bind(("::", 0))
  s.connect((s.getsockname()))
  sd = sock_diag.SockDiag()
  have_udp_diag = len(sd.DumpAllInetSockets(IPPROTO_UDP, "")) > 0
  s.close()
  return have_udp_diag

def HaveSctp():
  if net_test.LINUX_VERSION < (4, 7, 0):
    return False
  try:
    s = socket(AF_INET, SOCK_STREAM, IPPROTO_SCTP)
    s.close()
    return True
  except IOError:
    return False

HAVE_UDP_DIAG = HaveUdpDiag()
HAVE_SCTP = HaveSctp()


class SockDiagBaseTest(multinetwork_base.MultiNetworkBaseTest):
  """Basic tests for SOCK_DIAG functionality.

    Relevant kernel commits:
      android-3.4:
        ab4a727 net: inet_diag: zero out uninitialized idiag_{src,dst} fields
        99ee451 net: diag: support v4mapped sockets in inet_diag_find_one_icsk()

      android-3.10:
        3eb409b net: inet_diag: zero out uninitialized idiag_{src,dst} fields
        f77e059 net: diag: support v4mapped sockets in inet_diag_find_one_icsk()

      android-3.18:
        e603010 net: diag: support v4mapped sockets in inet_diag_find_one_icsk()

      android-4.4:
        525ee59 net: diag: support v4mapped sockets in inet_diag_find_one_icsk()
  """
  @staticmethod
  def _CreateLotsOfSockets(socktype):
    # Dict mapping (addr, sport, dport) tuples to socketpairs.
    socketpairs = {}
    for _ in xrange(NUM_SOCKETS):
      family, addr = random.choice([
          (AF_INET, "127.0.0.1"),
          (AF_INET6, "::1"),
          (AF_INET6, "::ffff:127.0.0.1")])
      socketpair = net_test.CreateSocketPair(family, socktype, addr)
      sport, dport = (socketpair[0].getsockname()[1],
                      socketpair[1].getsockname()[1])
      socketpairs[(addr, sport, dport)] = socketpair
    return socketpairs

  def assertSocketClosed(self, sock):
    self.assertRaisesErrno(ENOTCONN, sock.getpeername)

  def assertSocketConnected(self, sock):
    sock.getpeername()  # No errors? Socket is alive and connected.

  def assertSocketsClosed(self, socketpair):
    for sock in socketpair:
      self.assertSocketClosed(sock)

  def assertMarkIs(self, mark, attrs):
    self.assertEqual(mark, attrs.get("INET_DIAG_MARK", None))

  def assertSockInfoMatchesSocket(self, s, info):
    diag_msg, attrs = info
    family = s.getsockopt(net_test.SOL_SOCKET, net_test.SO_DOMAIN)
    self.assertEqual(diag_msg.family, family)

    src, sport = s.getsockname()[0:2]
    self.assertEqual(diag_msg.id.src, self.sock_diag.PaddedAddress(src))
    self.assertEqual(diag_msg.id.sport, sport)

    if self.sock_diag.GetDestinationAddress(diag_msg) not in ["0.0.0.0", "::"]:
      dst, dport = s.getpeername()[0:2]
      self.assertEqual(diag_msg.id.dst, self.sock_diag.PaddedAddress(dst))
      self.assertEqual(diag_msg.id.dport, dport)
    else:
      self.assertRaisesErrno(ENOTCONN, s.getpeername)

    mark = s.getsockopt(SOL_SOCKET, net_test.SO_MARK)
    self.assertMarkIs(mark, attrs)

  def PackAndCheckBytecode(self, instructions):
    bytecode = self.sock_diag.PackBytecode(instructions)
    decoded = self.sock_diag.DecodeBytecode(bytecode)
    self.assertEquals(len(instructions), len(decoded))
    self.assertFalse("???" in decoded)
    return bytecode

  def _EventDuringBlockingCall(self, sock, call, expected_errno, event):
    """Simulates an external event during a blocking call on sock.

    Args:
      sock: The socket to use.
      call: A function, the call to make. Takes one parameter, sock.
      expected_errno: The value that call is expected to fail with, or None if
        call is expected to succeed.
      event: A function, the event that will happen during the blocking call.
        Takes one parameter, sock.
    """
    thread = SocketExceptionThread(sock, call)
    thread.start()
    time.sleep(0.1)
    event(sock)
    thread.join(1)
    self.assertFalse(thread.is_alive())
    if expected_errno is not None:
      self.assertIsNotNone(thread.exception)
      self.assertTrue(isinstance(thread.exception, IOError),
                      "Expected IOError, got %s" % thread.exception)
      self.assertEqual(expected_errno, thread.exception.errno)
    else:
      self.assertIsNone(thread.exception)
    self.assertSocketClosed(sock)

  def CloseDuringBlockingCall(self, sock, call, expected_errno):
    self._EventDuringBlockingCall(
        sock, call, expected_errno,
        lambda sock: self.sock_diag.CloseSocketFromFd(sock))

  def setUp(self):
    super(SockDiagBaseTest, self).setUp()
    self.sock_diag = sock_diag.SockDiag()
    self.socketpairs = {}

  def tearDown(self):
    for socketpair in self.socketpairs.values():
      for s in socketpair:
        s.close()
    super(SockDiagBaseTest, self).tearDown()


class SockDiagTest(SockDiagBaseTest):

  def testFindsMappedSockets(self):
    """Tests that inet_diag_find_one_icsk can find mapped sockets."""
    socketpair = net_test.CreateSocketPair(AF_INET6, SOCK_STREAM,
                                           "::ffff:127.0.0.1")
    for sock in socketpair:
      diag_msg = self.sock_diag.FindSockDiagFromFd(sock)
      diag_req = self.sock_diag.DiagReqFromDiagMsg(diag_msg, IPPROTO_TCP)
      self.sock_diag.GetSockInfo(diag_req)
      # No errors? Good.

  def CheckFindsAllMySockets(self, socktype, proto):
    """Tests that basic socket dumping works."""
    self.socketpairs = self._CreateLotsOfSockets(socktype)
    sockets = self.sock_diag.DumpAllInetSockets(proto, NO_BYTECODE)
    self.assertGreaterEqual(len(sockets), NUM_SOCKETS)

    # Find the cookies for all of our sockets.
    cookies = {}
    for diag_msg, unused_attrs in sockets:
      addr = self.sock_diag.GetSourceAddress(diag_msg)
      sport = diag_msg.id.sport
      dport = diag_msg.id.dport
      if (addr, sport, dport) in self.socketpairs:
        cookies[(addr, sport, dport)] = diag_msg.id.cookie
      elif (addr, dport, sport) in self.socketpairs:
        cookies[(addr, sport, dport)] = diag_msg.id.cookie

    # Did we find all the cookies?
    self.assertEquals(2 * NUM_SOCKETS, len(cookies))

    socketpairs = self.socketpairs.values()
    random.shuffle(socketpairs)
    for socketpair in socketpairs:
      for sock in socketpair:
        # Check that we can find a diag_msg by scanning a dump.
        self.assertSockInfoMatchesSocket(
            sock,
            self.sock_diag.FindSockInfoFromFd(sock))
        cookie = self.sock_diag.FindSockDiagFromFd(sock).id.cookie

        # Check that we can find a diag_msg once we know the cookie.
        req = self.sock_diag.DiagReqFromSocket(sock)
        req.id.cookie = cookie
        if proto == IPPROTO_UDP:
          # Kernel bug: for UDP sockets, the order of arguments must be swapped.
          # See testDemonstrateUdpGetSockIdBug.
          req.id.sport, req.id.dport = req.id.dport, req.id.sport
          req.id.src, req.id.dst = req.id.dst, req.id.src
        info = self.sock_diag.GetSockInfo(req)
        self.assertSockInfoMatchesSocket(sock, info)

  def testFindsAllMySocketsTcp(self):
    self.CheckFindsAllMySockets(SOCK_STREAM, IPPROTO_TCP)

  @unittest.skipUnless(HAVE_UDP_DIAG, "INET_UDP_DIAG not enabled")
  def testFindsAllMySocketsUdp(self):
    self.CheckFindsAllMySockets(SOCK_DGRAM, IPPROTO_UDP)

  def testBytecodeCompilation(self):
    # pylint: disable=bad-whitespace
    instructions = [
        (sock_diag.INET_DIAG_BC_S_GE,   1, 8, 0),                      # 0
        (sock_diag.INET_DIAG_BC_D_LE,   1, 7, 0xffff),                 # 8
        (sock_diag.INET_DIAG_BC_S_COND, 1, 2, ("::1", 128, -1)),       # 16
        (sock_diag.INET_DIAG_BC_JMP,    1, 3, None),                   # 44
        (sock_diag.INET_DIAG_BC_S_COND, 2, 4, ("127.0.0.1", 32, -1)),  # 48
        (sock_diag.INET_DIAG_BC_D_LE,   1, 3, 0x6665),  # not used     # 64
        (sock_diag.INET_DIAG_BC_NOP,    1, 1, None),                   # 72
                                                                       # 76 acc
                                                                       # 80 rej
    ]
    # pylint: enable=bad-whitespace
    bytecode = self.PackAndCheckBytecode(instructions)
    expected = (
        "0208500000000000"
        "050848000000ffff"
        "071c20000a800000ffffffff00000000000000000000000000000001"
        "01041c00"
        "0718200002200000ffffffff7f000001"
        "0508100000006566"
        "00040400"
    )
    states = 1 << tcp_test.TCP_ESTABLISHED
    self.assertMultiLineEqual(expected, bytecode.encode("hex"))
    self.assertEquals(76, len(bytecode))
    self.socketpairs = self._CreateLotsOfSockets(SOCK_STREAM)
    filteredsockets = self.sock_diag.DumpAllInetSockets(IPPROTO_TCP, bytecode,
                                                        states=states)
    allsockets = self.sock_diag.DumpAllInetSockets(IPPROTO_TCP, NO_BYTECODE,
                                                   states=states)
    self.assertItemsEqual(allsockets, filteredsockets)

    # Pick a few sockets in hash table order, and check that the bytecode we
    # compiled selects them properly.
    for socketpair in self.socketpairs.values()[:20]:
      for s in socketpair:
        diag_msg = self.sock_diag.FindSockDiagFromFd(s)
        instructions = [
            (sock_diag.INET_DIAG_BC_S_GE, 1, 5, diag_msg.id.sport),
            (sock_diag.INET_DIAG_BC_S_LE, 1, 4, diag_msg.id.sport),
            (sock_diag.INET_DIAG_BC_D_GE, 1, 3, diag_msg.id.dport),
            (sock_diag.INET_DIAG_BC_D_LE, 1, 2, diag_msg.id.dport),
        ]
        bytecode = self.PackAndCheckBytecode(instructions)
        self.assertEquals(32, len(bytecode))
        sockets = self.sock_diag.DumpAllInetSockets(IPPROTO_TCP, bytecode)
        self.assertEquals(1, len(sockets))

        # TODO: why doesn't comparing the cstructs work?
        self.assertEquals(diag_msg.Pack(), sockets[0][0].Pack())

  def testCrossFamilyBytecode(self):
    """Checks for a cross-family bug in inet_diag_hostcond matching.

    Relevant kernel commits:
      android-3.4:
        f67caec inet_diag: avoid unsafe and nonsensical prefix matches in inet_diag_bc_run()
    """
    # TODO: this is only here because the test fails if there are any open
    # sockets other than the ones it creates itself. Make the bytecode more
    # specific and remove it.
    states = 1 << tcp_test.TCP_ESTABLISHED
    self.assertFalse(self.sock_diag.DumpAllInetSockets(IPPROTO_TCP, "",
                                                       states=states))

    unused_pair4 = net_test.CreateSocketPair(AF_INET, SOCK_STREAM, "127.0.0.1")
    unused_pair6 = net_test.CreateSocketPair(AF_INET6, SOCK_STREAM, "::1")

    bytecode4 = self.PackAndCheckBytecode([
        (sock_diag.INET_DIAG_BC_S_COND, 1, 2, ("0.0.0.0", 0, -1))])
    bytecode6 = self.PackAndCheckBytecode([
        (sock_diag.INET_DIAG_BC_S_COND, 1, 2, ("::", 0, -1))])

    # IPv4/v6 filters must never match IPv6/IPv4 sockets...
    v4socks = self.sock_diag.DumpAllInetSockets(IPPROTO_TCP, bytecode4,
                                                  states=states)
    self.assertTrue(v4socks)
    self.assertTrue(all(d.family == AF_INET for d, _ in v4socks))

    v6socks = self.sock_diag.DumpAllInetSockets(IPPROTO_TCP, bytecode6,
                                                  states=states)
    self.assertTrue(v6socks)
    self.assertTrue(all(d.family == AF_INET6 for d, _ in v6socks))

    # Except for mapped addresses, which match both IPv4 and IPv6.
    pair5 = net_test.CreateSocketPair(AF_INET6, SOCK_STREAM,
                                      "::ffff:127.0.0.1")
    diag_msgs = [self.sock_diag.FindSockDiagFromFd(s) for s in pair5]
    v4socks = [d for d, _ in self.sock_diag.DumpAllInetSockets(IPPROTO_TCP,
                                                               bytecode4,
                                                               states=states)]
    v6socks = [d for d, _ in self.sock_diag.DumpAllInetSockets(IPPROTO_TCP,
                                                               bytecode6,
                                                               states=states)]
    self.assertTrue(all(d in v4socks for d in diag_msgs))
    self.assertTrue(all(d in v6socks for d in diag_msgs))

  def testPortComparisonValidation(self):
    """Checks for a bug in validating port comparison bytecode.

    Relevant kernel commits:
      android-3.4:
        5e1f542 inet_diag: validate port comparison byte code to prevent unsafe reads
    """
    bytecode = sock_diag.InetDiagBcOp((sock_diag.INET_DIAG_BC_D_GE, 4, 8))
    self.assertEquals("???",
                      self.sock_diag.DecodeBytecode(bytecode))
    self.assertRaisesErrno(
        EINVAL,
        self.sock_diag.DumpAllInetSockets, IPPROTO_TCP, bytecode.Pack())

  def testNonSockDiagCommand(self):
    def DiagDump(code):
      sock_id = self.sock_diag._EmptyInetDiagSockId()
      req = sock_diag.InetDiagReqV2((AF_INET6, IPPROTO_TCP, 0, 0xffffffff,
                                     sock_id))
      self.sock_diag._Dump(code, req, sock_diag.InetDiagMsg, "")

    op = sock_diag.SOCK_DIAG_BY_FAMILY
    DiagDump(op)  # No errors? Good.
    self.assertRaisesErrno(EINVAL, DiagDump, op + 17)

  def CheckSocketCookie(self, inet, addr):
    """Tests that getsockopt SO_COOKIE can get cookie for all sockets."""
    socketpair = net_test.CreateSocketPair(inet, SOCK_STREAM, addr)
    for sock in socketpair:
      diag_msg = self.sock_diag.FindSockDiagFromFd(sock)
      cookie = sock.getsockopt(net_test.SOL_SOCKET, net_test.SO_COOKIE, 8)
      self.assertEqual(diag_msg.id.cookie, cookie)

  @unittest.skipUnless(LINUX_4_9_OR_ABOVE, "SO_COOKIE not supported")
  def testGetsockoptcookie(self):
    self.CheckSocketCookie(AF_INET, "127.0.0.1")
    self.CheckSocketCookie(AF_INET6, "::1")

  @unittest.skipUnless(HAVE_UDP_DIAG, "INET_UDP_DIAG not enabled")
  def testDemonstrateUdpGetSockIdBug(self):
    # TODO: this is because udp_dump_one mistakenly uses __udp[46]_lib_lookup
    # by passing the source address as the source address argument.
    # Unfortunately those functions are intended to match local sockets based
    # on received packets, and the argument that ends up being compared with
    # e.g., sk_daddr is actually saddr, not daddr. udp_diag_destroy does not
    # have this bug.  Upstream has confirmed that this will not be fixed:
    # https://www.mail-archive.com/netdev@vger.kernel.org/msg248638.html
    """Documents a bug: getting UDP sockets requires swapping src and dst."""
    for version in [4, 5, 6]:
      family = net_test.GetAddressFamily(version)
      s = socket(family, SOCK_DGRAM, 0)
      self.SelectInterface(s, self.RandomNetid(), "mark")
      s.connect((self.GetRemoteSocketAddress(version), 53))

      # Create a fully-specified diag req from our socket, including cookie if
      # we can get it.
      req = self.sock_diag.DiagReqFromSocket(s)
      if LINUX_4_9_OR_ABOVE:
        req.id.cookie = s.getsockopt(net_test.SOL_SOCKET, net_test.SO_COOKIE, 8)
      else:
        req.id.cookie = "\xff" * 16  # INET_DIAG_NOCOOKIE[2]

      # As is, this request does not find anything.
      with self.assertRaisesErrno(ENOENT):
        self.sock_diag.GetSockInfo(req)

      # But if we swap src and dst, the kernel finds our socket.
      req.id.sport, req.id.dport = req.id.dport, req.id.sport
      req.id.src, req.id.dst = req.id.dst, req.id.src

      self.assertSockInfoMatchesSocket(s, self.sock_diag.GetSockInfo(req))


class SockDestroyTest(SockDiagBaseTest):
  """Tests that SOCK_DESTROY works correctly.

  Relevant kernel commits:
    net-next:
      b613f56 net: diag: split inet_diag_dump_one_icsk into two
      64be0ae net: diag: Add the ability to destroy a socket.
      6eb5d2e net: diag: Support SOCK_DESTROY for inet sockets.
      c1e64e2 net: diag: Support destroying TCP sockets.
      2010b93 net: tcp: deal with listen sockets properly in tcp_abort.

    android-3.4:
      d48ec88 net: diag: split inet_diag_dump_one_icsk into two
      2438189 net: diag: Add the ability to destroy a socket.
      7a2ddbc net: diag: Support SOCK_DESTROY for inet sockets.
      44047b2 net: diag: Support destroying TCP sockets.
      200dae7 net: tcp: deal with listen sockets properly in tcp_abort.

    android-3.10:
      9eaff90 net: diag: split inet_diag_dump_one_icsk into two
      d60326c net: diag: Add the ability to destroy a socket.
      3d4ce85 net: diag: Support SOCK_DESTROY for inet sockets.
      529dfc6 net: diag: Support destroying TCP sockets.
      9c712fe net: tcp: deal with listen sockets properly in tcp_abort.

    android-3.18:
      100263d net: diag: split inet_diag_dump_one_icsk into two
      194c5f3 net: diag: Add the ability to destroy a socket.
      8387ea2 net: diag: Support SOCK_DESTROY for inet sockets.
      b80585a net: diag: Support destroying TCP sockets.
      476c6ce net: tcp: deal with listen sockets properly in tcp_abort.

    android-4.1:
      56eebf8 net: diag: split inet_diag_dump_one_icsk into two
      fb486c9 net: diag: Add the ability to destroy a socket.
      0c02b7e net: diag: Support SOCK_DESTROY for inet sockets.
      67c71d8 net: diag: Support destroying TCP sockets.
      a76e0ec net: tcp: deal with listen sockets properly in tcp_abort.
      e6e277b net: diag: support v4mapped sockets in inet_diag_find_one_icsk()

    android-4.4:
      76c83a9 net: diag: split inet_diag_dump_one_icsk into two
      f7cf791 net: diag: Add the ability to destroy a socket.
      1c42248 net: diag: Support SOCK_DESTROY for inet sockets.
      c9e8440d net: diag: Support destroying TCP sockets.
      3d9502c tcp: diag: add support for request sockets to tcp_abort()
      001cf75 net: tcp: deal with listen sockets properly in tcp_abort.
  """

  def testClosesSockets(self):
    self.socketpairs = self._CreateLotsOfSockets(SOCK_STREAM)
    for _, socketpair in self.socketpairs.iteritems():
      # Close one of the sockets.
      # This will send a RST that will close the other side as well.
      s = random.choice(socketpair)
      if random.randrange(0, 2) == 1:
        self.sock_diag.CloseSocketFromFd(s)
      else:
        diag_msg = self.sock_diag.FindSockDiagFromFd(s)

        # Get the cookie wrong and ensure that we get an error and the socket
        # is not closed.
        real_cookie = diag_msg.id.cookie
        diag_msg.id.cookie = os.urandom(len(real_cookie))
        req = self.sock_diag.DiagReqFromDiagMsg(diag_msg, IPPROTO_TCP)
        self.assertRaisesErrno(ENOENT, self.sock_diag.CloseSocket, req)
        self.assertSocketConnected(s)

        # Now close it with the correct cookie.
        req.id.cookie = real_cookie
        self.sock_diag.CloseSocket(req)

      # Check that both sockets in the pair are closed.
      self.assertSocketsClosed(socketpair)

  # TODO:
  # Test that killing unix sockets returns EOPNOTSUPP.


class SocketExceptionThread(threading.Thread):

  def __init__(self, sock, operation):
    self.exception = None
    super(SocketExceptionThread, self).__init__()
    self.daemon = True
    self.sock = sock
    self.operation = operation

  def run(self):
    try:
      self.operation(self.sock)
    except (IOError, AssertionError), e:
      self.exception = e


class SockDiagTcpTest(tcp_test.TcpBaseTest, SockDiagBaseTest):

  def testIpv4MappedSynRecvSocket(self):
    """Tests for the absence of a bug with AF_INET6 TCP SYN-RECV sockets.

    Relevant kernel commits:
         android-3.4:
           457a04b inet_diag: fix oops for IPv4 AF_INET6 TCP SYN-RECV state
    """
    netid = random.choice(self.tuns.keys())
    self.IncomingConnection(5, tcp_test.TCP_SYN_RECV, netid)
    sock_id = self.sock_diag._EmptyInetDiagSockId()
    sock_id.sport = self.port
    states = 1 << tcp_test.TCP_SYN_RECV
    req = sock_diag.InetDiagReqV2((AF_INET6, IPPROTO_TCP, 0, states, sock_id))
    children = self.sock_diag.Dump(req, NO_BYTECODE)

    self.assertTrue(children)
    for child, unused_args in children:
      self.assertEqual(tcp_test.TCP_SYN_RECV, child.state)
      self.assertEqual(self.sock_diag.PaddedAddress(self.remotesockaddr),
                       child.id.dst)
      self.assertEqual(self.sock_diag.PaddedAddress(self.mysockaddr),
                       child.id.src)


class TcpRcvWindowTest(tcp_test.TcpBaseTest, SockDiagBaseTest):

  RWND_SIZE = 64000 if LINUX_4_19_OR_ABOVE else 42000
  TCP_DEFAULT_INIT_RWND = "/proc/sys/net/ipv4/tcp_default_init_rwnd"

  def setUp(self):
    super(TcpRcvWindowTest, self).setUp()
    if LINUX_4_19_OR_ABOVE:
      self.assertRaisesErrno(ENOENT, open, self.TCP_DEFAULT_INIT_RWND, "w")
      return

    f = open(self.TCP_DEFAULT_INIT_RWND, "w")
    f.write("60")

  def checkInitRwndSize(self, version, netid):
    self.IncomingConnection(version, tcp_test.TCP_ESTABLISHED, netid)
    tcpInfo = TcpInfo(self.accepted.getsockopt(net_test.SOL_TCP,
                                               net_test.TCP_INFO, len(TcpInfo)))
    self.assertLess(self.RWND_SIZE, tcpInfo.tcpi_rcv_ssthresh,
                    "Tcp rwnd of netid=%d, version=%d is not enough. "
                    "Expect: %d, actual: %d" % (netid, version, self.RWND_SIZE,
                                                tcpInfo.tcpi_rcv_ssthresh))

  def checkSynPacketWindowSize(self, version, netid):
    s = self.BuildSocket(version, net_test.TCPSocket, netid, "mark")
    myaddr = self.MyAddress(version, netid)
    dstaddr = self.GetRemoteAddress(version)
    dstsockaddr = self.GetRemoteSocketAddress(version)
    desc, expected = packets.SYN(53, version, myaddr, dstaddr,
                                 sport=None, seq=None)
    self.assertRaisesErrno(EINPROGRESS, s.connect, (dstsockaddr, 53))
    msg = "IPv%s TCP connect: expected %s on %s" % (
        version, desc, self.GetInterfaceName(netid))
    syn = self.ExpectPacketOn(netid, msg, expected)
    self.assertLess(self.RWND_SIZE, syn.window)
    s.close()

  def testTcpCwndSize(self):
    for version in [4, 5, 6]:
      for netid in self.NETIDS:
        self.checkInitRwndSize(version, netid)
        self.checkSynPacketWindowSize(version, netid)


class SockDestroyTcpTest(tcp_test.TcpBaseTest, SockDiagBaseTest):

  def setUp(self):
    super(SockDestroyTcpTest, self).setUp()
    self.netid = random.choice(self.tuns.keys())

  def CheckRstOnClose(self, sock, req, expect_reset, msg, do_close=True):
    """Closes the socket and checks whether a RST is sent or not."""
    if sock is not None:
      self.assertIsNone(req, "Must specify sock or req, not both")
      self.sock_diag.CloseSocketFromFd(sock)
      self.assertRaisesErrno(EINVAL, sock.accept)
    else:
      self.assertIsNone(sock, "Must specify sock or req, not both")
      self.sock_diag.CloseSocket(req)

    if expect_reset:
      desc, rst = self.RstPacket()
      msg = "%s: expecting %s: " % (msg, desc)
      self.ExpectPacketOn(self.netid, msg, rst)
    else:
      msg = "%s: " % msg
      self.ExpectNoPacketsOn(self.netid, msg)

    if sock is not None and do_close:
      sock.close()

  def CheckTcpReset(self, state, statename):
    for version in [4, 5, 6]:
      msg = "Closing incoming IPv%d %s socket" % (version, statename)
      self.IncomingConnection(version, state, self.netid)
      self.CheckRstOnClose(self.s, None, False, msg)
      if state != tcp_test.TCP_LISTEN:
        msg = "Closing accepted IPv%d %s socket" % (version, statename)
        self.CheckRstOnClose(self.accepted, None, True, msg)

  def testTcpResets(self):
    """Checks that closing sockets in appropriate states sends a RST."""
    self.CheckTcpReset(tcp_test.TCP_LISTEN, "TCP_LISTEN")
    self.CheckTcpReset(tcp_test.TCP_ESTABLISHED, "TCP_ESTABLISHED")
    self.CheckTcpReset(tcp_test.TCP_CLOSE_WAIT, "TCP_CLOSE_WAIT")

  def testFinWait1Socket(self):
    for version in [4, 5, 6]:
      self.IncomingConnection(version, tcp_test.TCP_ESTABLISHED, self.netid)

      # Get the cookie so we can find this socket after we close it.
      diag_msg = self.sock_diag.FindSockDiagFromFd(self.accepted)
      diag_req = self.sock_diag.DiagReqFromDiagMsg(diag_msg, IPPROTO_TCP)

      # Close the socket and check that it goes into FIN_WAIT1 and sends a FIN.
      net_test.EnableFinWait(self.accepted)
      self.accepted.close()
      diag_req.states = 1 << tcp_test.TCP_FIN_WAIT1
      diag_msg, attrs = self.sock_diag.GetSockInfo(diag_req)
      self.assertEquals(tcp_test.TCP_FIN_WAIT1, diag_msg.state)
      desc, fin = self.FinPacket()
      self.ExpectPacketOn(self.netid, "Closing FIN_WAIT1 socket", fin)

      # Destroy the socket and expect no RST.
      self.CheckRstOnClose(None, diag_req, False, "Closing FIN_WAIT1 socket")
      diag_msg, attrs = self.sock_diag.GetSockInfo(diag_req)

      # The socket is still there in FIN_WAIT1: SOCK_DESTROY did nothing
      # because userspace had already closed it.
      self.assertEquals(tcp_test.TCP_FIN_WAIT1, diag_msg.state)

      # ACK the FIN so we don't trip over retransmits in future tests.
      finversion = 4 if version == 5 else version
      desc, finack = packets.ACK(finversion, self.remoteaddr, self.myaddr, fin)
      diag_msg, attrs = self.sock_diag.GetSockInfo(diag_req)
      self.ReceivePacketOn(self.netid, finack)

      # See if we can find the resulting FIN_WAIT2 socket. This does not appear
      # to work on 3.10.
      if net_test.LINUX_VERSION >= (3, 18):
        diag_req.states = 1 << tcp_test.TCP_FIN_WAIT2
        infos = self.sock_diag.Dump(diag_req, "")
        self.assertTrue(any(diag_msg.state == tcp_test.TCP_FIN_WAIT2
                            for diag_msg, attrs in infos),
                        "Expected to find FIN_WAIT2 socket in %s" % infos)

  def FindChildSockets(self, s):
    """Finds the SYN_RECV child sockets of a given listening socket."""
    d = self.sock_diag.FindSockDiagFromFd(self.s)
    req = self.sock_diag.DiagReqFromDiagMsg(d, IPPROTO_TCP)
    req.states = 1 << tcp_test.TCP_SYN_RECV | 1 << tcp_test.TCP_ESTABLISHED
    req.id.cookie = "\x00" * 8

    bad_bytecode = self.PackAndCheckBytecode(
        [(sock_diag.INET_DIAG_BC_MARK_COND, 1, 2, (0xffff, 0xffff))])
    self.assertEqual([], self.sock_diag.Dump(req, bad_bytecode))

    bytecode = self.PackAndCheckBytecode(
        [(sock_diag.INET_DIAG_BC_MARK_COND, 1, 2, (self.netid, 0xffff))])
    children = self.sock_diag.Dump(req, bytecode)
    return [self.sock_diag.DiagReqFromDiagMsg(d, IPPROTO_TCP)
            for d, _ in children]

  def CheckChildSocket(self, version, statename, parent_first):
    state = getattr(tcp_test, statename)

    self.IncomingConnection(version, state, self.netid)

    d = self.sock_diag.FindSockDiagFromFd(self.s)
    parent = self.sock_diag.DiagReqFromDiagMsg(d, IPPROTO_TCP)
    children = self.FindChildSockets(self.s)
    self.assertEquals(1, len(children))

    is_established = (state == tcp_test.TCP_NOT_YET_ACCEPTED)
    expected_state = tcp_test.TCP_ESTABLISHED if is_established else state

    # The new TCP listener code in 4.4 makes SYN_RECV sockets live in the
    # regular TCP hash tables, and inet_diag_find_one_icsk can find them.
    # Before 4.4, we can see those sockets in dumps, but we can't fetch
    # or close them.
    can_close_children = is_established or net_test.LINUX_VERSION >= (4, 4)

    for child in children:
      if can_close_children:
        diag_msg, attrs = self.sock_diag.GetSockInfo(child)
        self.assertEquals(diag_msg.state, expected_state)
        self.assertMarkIs(self.netid, attrs)
      else:
        self.assertRaisesErrno(ENOENT, self.sock_diag.GetSockInfo, child)

    def CloseParent(expect_reset):
      msg = "Closing parent IPv%d %s socket %s child" % (
          version, statename, "before" if parent_first else "after")
      self.CheckRstOnClose(self.s, None, expect_reset, msg)
      self.assertRaisesErrno(ENOENT, self.sock_diag.GetSockInfo, parent)

    def CheckChildrenClosed():
      for child in children:
        self.assertRaisesErrno(ENOENT, self.sock_diag.GetSockInfo, child)

    def CloseChildren():
      for child in children:
        msg = "Closing child IPv%d %s socket %s parent" % (
            version, statename, "after" if parent_first else "before")
        self.sock_diag.GetSockInfo(child)
        self.CheckRstOnClose(None, child, is_established, msg)
        self.assertRaisesErrno(ENOENT, self.sock_diag.GetSockInfo, child)
      CheckChildrenClosed()

    if parent_first:
      # Closing the parent will close child sockets, which will send a RST,
      # iff they are already established.
      CloseParent(is_established)
      if is_established:
        CheckChildrenClosed()
      elif can_close_children:
        CloseChildren()
        CheckChildrenClosed()
      self.s.close()
    else:
      if can_close_children:
        CloseChildren()
      CloseParent(False)
      self.s.close()

  def testChildSockets(self):
    for version in [4, 5, 6]:
      self.CheckChildSocket(version, "TCP_SYN_RECV", False)
      self.CheckChildSocket(version, "TCP_SYN_RECV", True)
      self.CheckChildSocket(version, "TCP_NOT_YET_ACCEPTED", False)
      self.CheckChildSocket(version, "TCP_NOT_YET_ACCEPTED", True)

  def testAcceptInterrupted(self):
    """Tests that accept() is interrupted by SOCK_DESTROY."""
    for version in [4, 5, 6]:
      self.IncomingConnection(version, tcp_test.TCP_LISTEN, self.netid)
      self.assertRaisesErrno(ENOTCONN, self.s.recv, 4096)
      self.CloseDuringBlockingCall(self.s, lambda sock: sock.accept(), EINVAL)
      self.assertRaisesErrno(ECONNABORTED, self.s.send, "foo")
      self.assertRaisesErrno(EINVAL, self.s.accept)
      # TODO: this should really return an error such as ENOTCONN...
      self.assertEquals("", self.s.recv(4096))

  def testReadInterrupted(self):
    """Tests that read() is interrupted by SOCK_DESTROY."""
    for version in [4, 5, 6]:
      self.IncomingConnection(version, tcp_test.TCP_ESTABLISHED, self.netid)
      self.CloseDuringBlockingCall(self.accepted, lambda sock: sock.recv(4096),
                                   ECONNABORTED)
      # Writing returns EPIPE, and reading returns EOF.
      self.assertRaisesErrno(EPIPE, self.accepted.send, "foo")
      self.assertEquals("", self.accepted.recv(4096))
      self.assertEquals("", self.accepted.recv(4096))

  def testConnectInterrupted(self):
    """Tests that connect() is interrupted by SOCK_DESTROY."""
    for version in [4, 5, 6]:
      family = {4: AF_INET, 5: AF_INET6, 6: AF_INET6}[version]
      s = net_test.Socket(family, SOCK_STREAM, IPPROTO_TCP)
      self.SelectInterface(s, self.netid, "mark")

      remotesockaddr = self.GetRemoteSocketAddress(version)
      remoteaddr = self.GetRemoteAddress(version)
      s.bind(("", 0))
      _, sport = s.getsockname()[:2]
      self.CloseDuringBlockingCall(
          s, lambda sock: sock.connect((remotesockaddr, 53)), ECONNABORTED)
      desc, syn = packets.SYN(53, version, self.MyAddress(version, self.netid),
                              remoteaddr, sport=sport, seq=None)
      self.ExpectPacketOn(self.netid, desc, syn)
      msg = "SOCK_DESTROY of socket in connect, expected no RST"
      self.ExpectNoPacketsOn(self.netid, msg)


class PollOnCloseTest(tcp_test.TcpBaseTest, SockDiagBaseTest):
  """Tests that the effect of SOCK_DESTROY on poll matches TCP RSTs.

  The behaviour of poll() in these cases is not what we might expect: if only
  POLLIN is specified, it will return POLLIN|POLLERR|POLLHUP, but if POLLOUT
  is (also) specified, it will only return POLLOUT.
  """

  POLLIN_OUT = select.POLLIN | select.POLLOUT
  POLLIN_ERR_HUP = select.POLLIN | select.POLLERR | select.POLLHUP

  def setUp(self):
    super(PollOnCloseTest, self).setUp()
    self.netid = random.choice(self.tuns.keys())

  POLL_FLAGS = [(select.POLLIN, "IN"), (select.POLLOUT, "OUT"),
                (select.POLLERR, "ERR"), (select.POLLHUP, "HUP")]

  def PollResultToString(self, poll_events, ignoremask):
    out = []
    for fd, event in poll_events:
      flags = [name for (flag, name) in self.POLL_FLAGS
               if event & flag & ~ignoremask != 0]
      out.append((fd, "|".join(flags)))
    return out

  def BlockingPoll(self, sock, mask, expected, ignoremask):
    p = select.poll()
    p.register(sock, mask)
    expected_fds = [(sock.fileno(), expected)]
    # Don't block forever or we'll hang continuous test runs on failure.
    # A 5-second timeout should be long enough not to be flaky.
    actual_fds = p.poll(5000)
    self.assertEqual(self.PollResultToString(expected_fds, ignoremask),
                     self.PollResultToString(actual_fds, ignoremask))

  def RstDuringBlockingCall(self, sock, call, expected_errno):
    self._EventDuringBlockingCall(
        sock, call, expected_errno,
        lambda _: self.ReceiveRstPacketOn(self.netid))

  def assertSocketErrors(self, errno):
    # The first operation returns the expected errno.
    self.assertRaisesErrno(errno, self.accepted.recv, 4096)

    # Subsequent operations behave as normal.
    self.assertRaisesErrno(EPIPE, self.accepted.send, "foo")
    self.assertEquals("", self.accepted.recv(4096))
    self.assertEquals("", self.accepted.recv(4096))

  def CheckPollDestroy(self, mask, expected, ignoremask):
    """Interrupts a poll() with SOCK_DESTROY."""
    for version in [4, 5, 6]:
      self.IncomingConnection(version, tcp_test.TCP_ESTABLISHED, self.netid)
      self.CloseDuringBlockingCall(
          self.accepted,
          lambda sock: self.BlockingPoll(sock, mask, expected, ignoremask),
          None)
      self.assertSocketErrors(ECONNABORTED)

  def CheckPollRst(self, mask, expected, ignoremask):
    """Interrupts a poll() by receiving a TCP RST."""
    for version in [4, 5, 6]:
      self.IncomingConnection(version, tcp_test.TCP_ESTABLISHED, self.netid)
      self.RstDuringBlockingCall(
          self.accepted,
          lambda sock: self.BlockingPoll(sock, mask, expected, ignoremask),
          None)
      self.assertSocketErrors(ECONNRESET)

  def testReadPollRst(self):
    # Until 3d4762639d ("tcp: remove poll() flakes when receiving RST"), poll()
    # would sometimes return POLLERR and sometimes POLLIN|POLLERR|POLLHUP. This
    # is due to a race inside the kernel and thus is not visible on the VM, only
    # on physical hardware.
    if net_test.LINUX_VERSION < (4, 14, 0):
      ignoremask = select.POLLIN | select.POLLHUP
    else:
      ignoremask = 0
    self.CheckPollRst(select.POLLIN, self.POLLIN_ERR_HUP, ignoremask)

  def testWritePollRst(self):
    self.CheckPollRst(select.POLLOUT, select.POLLOUT, 0)

  def testReadWritePollRst(self):
    self.CheckPollRst(self.POLLIN_OUT, select.POLLOUT, 0)

  def testReadPollDestroy(self):
    # tcp_abort has the same race that tcp_reset has, but it's not fixed yet.
    ignoremask = select.POLLIN | select.POLLHUP
    self.CheckPollDestroy(select.POLLIN, self.POLLIN_ERR_HUP, ignoremask)

  def testWritePollDestroy(self):
    self.CheckPollDestroy(select.POLLOUT, select.POLLOUT, 0)

  def testReadWritePollDestroy(self):
    self.CheckPollDestroy(self.POLLIN_OUT, select.POLLOUT, 0)


@unittest.skipUnless(HAVE_UDP_DIAG, "INET_UDP_DIAG not enabled")
class SockDestroyUdpTest(SockDiagBaseTest):

  """Tests SOCK_DESTROY on UDP sockets.

    Relevant kernel commits:
      upstream net-next:
        5d77dca net: diag: support SOCK_DESTROY for UDP sockets
        f95bf34 net: diag: make udp_diag_destroy work for mapped addresses.
  """

  def testClosesUdpSockets(self):
    self.socketpairs = self._CreateLotsOfSockets(SOCK_DGRAM)
    for _, socketpair in self.socketpairs.iteritems():
      s1, s2 = socketpair

      self.assertSocketConnected(s1)
      self.sock_diag.CloseSocketFromFd(s1)
      self.assertSocketClosed(s1)

      self.assertSocketConnected(s2)
      self.sock_diag.CloseSocketFromFd(s2)
      self.assertSocketClosed(s2)

  def BindToRandomPort(self, s, addr):
    ATTEMPTS = 20
    for i in xrange(20):
      port = random.randrange(1024, 65535)
      try:
        s.bind((addr, port))
        return port
      except error, e:
        if e.errno != EADDRINUSE:
          raise e
    raise ValueError("Could not find a free port on %s after %d attempts" %
                     (addr, ATTEMPTS))

  def testSocketAddressesAfterClose(self):
    for version in 4, 5, 6:
      netid = random.choice(self.NETIDS)
      dst = self.GetRemoteSocketAddress(version)
      family = {4: AF_INET, 5: AF_INET6, 6: AF_INET6}[version]
      unspec = {4: "0.0.0.0", 5: "::", 6: "::"}[version]

      # Closing a socket that was not explicitly bound (i.e., bound via
      # connect(), not bind()) clears the source address and port.
      s = self.BuildSocket(version, net_test.UDPSocket, netid, "mark")
      self.SelectInterface(s, netid, "mark")
      s.connect((dst, 53))
      self.sock_diag.CloseSocketFromFd(s)
      self.assertEqual((unspec, 0), s.getsockname()[:2])

      # Closing a socket bound to an IP address leaves the address as is.
      s = self.BuildSocket(version, net_test.UDPSocket, netid, "mark")
      src = self.MySocketAddress(version, netid)
      s.bind((src, 0))
      s.connect((dst, 53))
      port = s.getsockname()[1]
      self.sock_diag.CloseSocketFromFd(s)
      self.assertEqual((src, 0), s.getsockname()[:2])

      # Closing a socket bound to a port leaves the port as is.
      s = self.BuildSocket(version, net_test.UDPSocket, netid, "mark")
      port = self.BindToRandomPort(s, "")
      s.connect((dst, 53))
      self.sock_diag.CloseSocketFromFd(s)
      self.assertEqual((unspec, port), s.getsockname()[:2])

      # Closing a socket bound to IP address and port leaves both as is.
      s = self.BuildSocket(version, net_test.UDPSocket, netid, "mark")
      src = self.MySocketAddress(version, netid)
      port = self.BindToRandomPort(s, src)
      self.sock_diag.CloseSocketFromFd(s)
      self.assertEqual((src, port), s.getsockname()[:2])

  def testReadInterrupted(self):
    """Tests that read() is interrupted by SOCK_DESTROY."""
    for version in [4, 5, 6]:
      family = {4: AF_INET, 5: AF_INET6, 6: AF_INET6}[version]
      s = net_test.UDPSocket(family)
      self.SelectInterface(s, random.choice(self.NETIDS), "mark")
      addr = self.GetRemoteSocketAddress(version)

      # Check that reads on connected sockets are interrupted.
      s.connect((addr, 53))
      self.assertEquals(3, s.send("foo"))
      self.CloseDuringBlockingCall(s, lambda sock: sock.recv(4096),
                                   ECONNABORTED)

      # A destroyed socket is no longer connected, but still usable.
      self.assertRaisesErrno(EDESTADDRREQ, s.send, "foo")
      self.assertEquals(3, s.sendto("foo", (addr, 53)))

      # Check that reads on unconnected sockets are also interrupted.
      self.CloseDuringBlockingCall(s, lambda sock: sock.recv(4096),
                                   ECONNABORTED)

class SockDestroyPermissionTest(SockDiagBaseTest):

  def CheckPermissions(self, socktype):
    s = socket(AF_INET6, socktype, 0)
    self.SelectInterface(s, random.choice(self.NETIDS), "mark")
    if socktype == SOCK_STREAM:
      s.listen(1)
      expectedstate = tcp_test.TCP_LISTEN
    else:
      s.connect((self.GetRemoteAddress(6), 53))
      expectedstate = tcp_test.TCP_ESTABLISHED

    with net_test.RunAsUid(12345):
      self.assertRaisesErrno(
          EPERM, self.sock_diag.CloseSocketFromFd, s)

    self.sock_diag.CloseSocketFromFd(s)
    self.assertRaises(ValueError, self.sock_diag.CloseSocketFromFd, s)


  @unittest.skipUnless(HAVE_UDP_DIAG, "INET_UDP_DIAG not enabled")
  def testUdp(self):
    self.CheckPermissions(SOCK_DGRAM)

  def testTcp(self):
    self.CheckPermissions(SOCK_STREAM)


class SockDiagMarkTest(tcp_test.TcpBaseTest, SockDiagBaseTest):

  """Tests SOCK_DIAG bytecode filters that use marks.

    Relevant kernel commits:
      upstream net-next:
        627cc4a net: diag: slightly refactor the inet_diag_bc_audit error checks.
        a52e95a net: diag: allow socket bytecode filters to match socket marks
        d545cac net: inet: diag: expose the socket mark to privileged processes.
  """

  def FilterEstablishedSockets(self, mark, mask):
    instructions = [(sock_diag.INET_DIAG_BC_MARK_COND, 1, 2, (mark, mask))]
    bytecode = self.sock_diag.PackBytecode(instructions)
    return self.sock_diag.DumpAllInetSockets(
        IPPROTO_TCP, bytecode, states=(1 << tcp_test.TCP_ESTABLISHED))

  def assertSamePorts(self, ports, diag_msgs):
    expected = sorted(ports)
    actual = sorted([msg[0].id.sport for msg in diag_msgs])
    self.assertEquals(expected, actual)

  def SockInfoMatchesSocket(self, s, info):
    try:
      self.assertSockInfoMatchesSocket(s, info)
      return True
    except AssertionError:
      return False

  @staticmethod
  def SocketDescription(s):
    return "%s -> %s" % (str(s.getsockname()), str(s.getpeername()))

  def assertFoundSockets(self, infos, sockets):
    matches = {}
    for s in sockets:
      match = None
      for info in infos:
        if self.SockInfoMatchesSocket(s, info):
          if match:
            self.fail("Socket %s matched both %s and %s" %
                      (self.SocketDescription(s), match, info))
          matches[s] = info
      self.assertTrue(s in matches, "Did not find socket %s in dump" %
                      self.SocketDescription(s))

    for i in infos:
       if i not in matches.values():
         self.fail("Too many sockets in dump, first unexpected: %s" % str(i))

  def testMarkBytecode(self):
    family, addr = random.choice([
        (AF_INET, "127.0.0.1"),
        (AF_INET6, "::1"),
        (AF_INET6, "::ffff:127.0.0.1")])
    s1, s2 = net_test.CreateSocketPair(family, SOCK_STREAM, addr)
    s1.setsockopt(SOL_SOCKET, net_test.SO_MARK, 0xfff1234)
    s2.setsockopt(SOL_SOCKET, net_test.SO_MARK, 0xf0f1235)

    infos = self.FilterEstablishedSockets(0x1234, 0xffff)
    self.assertFoundSockets(infos, [s1])

    infos = self.FilterEstablishedSockets(0x1234, 0xfffe)
    self.assertFoundSockets(infos, [s1, s2])

    infos = self.FilterEstablishedSockets(0x1235, 0xffff)
    self.assertFoundSockets(infos, [s2])

    infos = self.FilterEstablishedSockets(0x0, 0x0)
    self.assertFoundSockets(infos, [s1, s2])

    infos = self.FilterEstablishedSockets(0xfff0000, 0xf0fed00)
    self.assertEquals(0, len(infos))

    with net_test.RunAsUid(12345):
        self.assertRaisesErrno(EPERM, self.FilterEstablishedSockets,
                               0xfff0000, 0xf0fed00)

  @staticmethod
  def SetRandomMark(s):
    # Python doesn't like marks that don't fit into a signed int.
    mark = random.randrange(0, 2**31 - 1)
    s.setsockopt(SOL_SOCKET, net_test.SO_MARK, mark)
    return mark

  def assertSocketMarkIs(self, s, mark):
    diag_msg, attrs = self.sock_diag.FindSockInfoFromFd(s)
    self.assertMarkIs(mark, attrs)
    with net_test.RunAsUid(12345):
      diag_msg, attrs = self.sock_diag.FindSockInfoFromFd(s)
      self.assertMarkIs(None, attrs)

  def testMarkInAttributes(self):
    testcases = [(AF_INET, "127.0.0.1"),
                 (AF_INET6, "::1"),
                 (AF_INET6, "::ffff:127.0.0.1")]
    for family, addr in testcases:
      # TCP listen sockets.
      server = socket(family, SOCK_STREAM, 0)
      server.bind((addr, 0))
      port = server.getsockname()[1]
      server.listen(1)  # Or the socket won't be in the hashtables.
      server_mark = self.SetRandomMark(server)
      self.assertSocketMarkIs(server, server_mark)

      # TCP client sockets.
      client = socket(family, SOCK_STREAM, 0)
      client_mark = self.SetRandomMark(client)
      client.connect((addr, port))
      self.assertSocketMarkIs(client, client_mark)

      # TCP server sockets.
      accepted, _ = server.accept()
      self.assertSocketMarkIs(accepted, server_mark)

      accepted_mark = self.SetRandomMark(accepted)
      self.assertSocketMarkIs(accepted, accepted_mark)
      self.assertSocketMarkIs(server, server_mark)

      server.close()
      client.close()

      # Other TCP states are tested in SockDestroyTcpTest.

      # UDP sockets.
      if HAVE_UDP_DIAG:
        s = socket(family, SOCK_DGRAM, 0)
        mark = self.SetRandomMark(s)
        s.connect(("", 53))
        self.assertSocketMarkIs(s, mark)
        s.close()

      # Basic test for SCTP. sctp_diag was only added in 4.7.
      if HAVE_SCTP:
        s = socket(family, SOCK_STREAM, IPPROTO_SCTP)
        s.bind((addr, 0))
        s.listen(1)
        mark = self.SetRandomMark(s)
        self.assertSocketMarkIs(s, mark)
        sockets = self.sock_diag.DumpAllInetSockets(IPPROTO_SCTP, NO_BYTECODE)
        self.assertEqual(1, len(sockets))
        self.assertEqual(mark, sockets[0][1].get("INET_DIAG_MARK", None))
        s.close()


if __name__ == "__main__":
  unittest.main()
