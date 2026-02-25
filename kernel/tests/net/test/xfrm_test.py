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

# pylint: disable=g-bad-todo,g-bad-file-header,wildcard-import
from errno import *  # pylint: disable=wildcard-import
from scapy import all as scapy
from socket import *  # pylint: disable=wildcard-import
import struct
import subprocess
import threading
import unittest

import csocket
import cstruct
import multinetwork_base
import net_test
import packets
import xfrm
import xfrm_base

ENCRYPTED_PAYLOAD = ("b1c74998efd6326faebe2061f00f2c750e90e76001664a80c287b150"
                     "59e74bf949769cc6af71e51b539e7de3a2a14cb05a231b969e035174"
                     "d98c5aa0cef1937db98889ec0d08fa408fecf616")

TEST_ADDR1 = "2001:4860:4860::8888"
TEST_ADDR2 = "2001:4860:4860::8844"

XFRM_STATS_PROCFILE = "/proc/net/xfrm_stat"
XFRM_STATS_OUT_NO_STATES = "XfrmOutNoStates"

# IP addresses to use for tunnel endpoints. For generality, these should be
# different from the addresses we send packets to.
TUNNEL_ENDPOINTS = {4: "8.8.4.4", 6: TEST_ADDR2}

TEST_SPI = 0x1234
TEST_SPI2 = 0x1235



class XfrmFunctionalTest(xfrm_base.XfrmLazyTest):

  def assertIsUdpEncapEsp(self, packet, spi, seq, length):
    self.assertEquals(IPPROTO_UDP, packet.proto)
    udp_hdr = packet[scapy.UDP]
    self.assertEquals(4500, udp_hdr.dport)
    self.assertEquals(length, len(udp_hdr))
    esp_hdr, _ = cstruct.Read(str(udp_hdr.payload), xfrm.EspHdr)
    # FIXME: this file currently swaps SPI byte order manually, so SPI needs to
    # be double-swapped here.
    self.assertEquals(xfrm.EspHdr((spi, seq)), esp_hdr)

  def CreateNewSa(self, localAddr, remoteAddr, spi, reqId, encap_tmpl,
                  null_auth=False):
    auth_algo = (
        xfrm_base._ALGO_AUTH_NULL if null_auth else xfrm_base._ALGO_HMAC_SHA1)
    self.xfrm.AddSaInfo(localAddr, remoteAddr, spi, xfrm.XFRM_MODE_TRANSPORT,
                    reqId, xfrm_base._ALGO_CBC_AES_256, auth_algo, None,
                    encap_tmpl, None, None)

  def testAddSa(self):
    self.CreateNewSa("::", TEST_ADDR1, TEST_SPI, 3320, None)
    expected = (
        "src :: dst 2001:4860:4860::8888\n"
        "\tproto esp spi 0x00001234 reqid 3320 mode transport\n"
        "\treplay-window 4 \n"
        "\tauth-trunc hmac(sha1) 0x%s 96\n"
        "\tenc cbc(aes) 0x%s\n"
        "\tsel src ::/0 dst ::/0 \n" % (
            xfrm_base._AUTHENTICATION_KEY_128.encode("hex"),
            xfrm_base._ENCRYPTION_KEY_256.encode("hex")))

    actual = subprocess.check_output("ip xfrm state".split())
    # Newer versions of IP also show anti-replay context. Don't choke if it's
    # missing.
    actual = actual.replace(
        "\tanti-replay context: seq 0x0, oseq 0x0, bitmap 0x00000000\n", "")
    try:
      self.assertMultiLineEqual(expected, actual)
    finally:
      self.xfrm.DeleteSaInfo(TEST_ADDR1, TEST_SPI, IPPROTO_ESP)

  def testFlush(self):
    self.assertEquals(0, len(self.xfrm.DumpSaInfo()))
    self.CreateNewSa("::", "2000::", TEST_SPI, 1234, None)
    self.CreateNewSa("0.0.0.0", "192.0.2.1", TEST_SPI, 4321, None)
    self.assertEquals(2, len(self.xfrm.DumpSaInfo()))
    self.xfrm.FlushSaInfo()
    self.assertEquals(0, len(self.xfrm.DumpSaInfo()))

  def _TestSocketPolicy(self, version):
    # Open a UDP socket and connect it.
    family = net_test.GetAddressFamily(version)
    s = socket(family, SOCK_DGRAM, 0)
    netid = self.RandomNetid()
    self.SelectInterface(s, netid, "mark")

    remotesockaddr = self.GetRemoteSocketAddress(version)
    s.connect((remotesockaddr, 53))
    saddr, sport = s.getsockname()[:2]
    daddr, dport = s.getpeername()[:2]
    if version == 5:
      saddr = saddr.replace("::ffff:", "")
      daddr = daddr.replace("::ffff:", "")

    reqid = 0

    desc, pkt = packets.UDP(version, saddr, daddr, sport=sport)
    s.sendto(net_test.UDP_PAYLOAD, (remotesockaddr, 53))
    self.ExpectPacketOn(netid, "Send after socket, expected %s" % desc, pkt)

    # Using IPv4 XFRM on a dual-stack socket requires setting an AF_INET policy
    # that's written in terms of IPv4 addresses.
    xfrm_version = 4 if version == 5 else version
    xfrm_family = net_test.GetAddressFamily(xfrm_version)
    xfrm_base.ApplySocketPolicy(s, xfrm_family, xfrm.XFRM_POLICY_OUT,
                                TEST_SPI, reqid, None)

    # Because the policy has level set to "require" (the default), attempting
    # to send a packet results in an error, because there is no SA that
    # matches the socket policy we set.
    self.assertRaisesErrno(
        EAGAIN,
        s.sendto, net_test.UDP_PAYLOAD, (remotesockaddr, 53))

    # If there is a user space key manager, calling sendto() after applying the socket policy
    # creates an SA whose state is XFRM_STATE_ACQ. So this just deletes it.
    # If there is no user space key manager, deleting SA returns ESRCH as the error code.
    try:
        self.xfrm.DeleteSaInfo(self.GetRemoteAddress(xfrm_version), TEST_SPI, IPPROTO_ESP)
    except IOError as e:
        self.assertEquals(ESRCH, e.errno, "Unexpected error when deleting ACQ SA")

    # Adding a matching SA causes the packet to go out encrypted. The SA's
    # SPI must match the one in our template, and the destination address must
    # match the packet's destination address (in tunnel mode, it has to match
    # the tunnel destination).
    self.CreateNewSa(
        net_test.GetWildcardAddress(xfrm_version),
        self.GetRemoteAddress(xfrm_version), TEST_SPI, reqid, None)

    s.sendto(net_test.UDP_PAYLOAD, (remotesockaddr, 53))
    expected_length = xfrm_base.GetEspPacketLength(xfrm.XFRM_MODE_TRANSPORT,
                                                version, False,
                                                net_test.UDP_PAYLOAD,
                                                xfrm_base._ALGO_HMAC_SHA1,
                                                xfrm_base._ALGO_CBC_AES_256)
    self._ExpectEspPacketOn(netid, TEST_SPI, 1, expected_length, None, None)

    # Sending to another destination doesn't work: again, no matching SA.
    remoteaddr2 = self.GetOtherRemoteSocketAddress(version)
    self.assertRaisesErrno(
        EAGAIN,
        s.sendto, net_test.UDP_PAYLOAD, (remoteaddr2, 53))

    # Sending on another socket without the policy applied results in an
    # unencrypted packet going out.
    s2 = socket(family, SOCK_DGRAM, 0)
    self.SelectInterface(s2, netid, "mark")
    s2.sendto(net_test.UDP_PAYLOAD, (remotesockaddr, 53))
    pkts = self.ReadAllPacketsOn(netid)
    self.assertEquals(1, len(pkts))
    packet = pkts[0]

    protocol = packet.nh if version == 6 else packet.proto
    self.assertEquals(IPPROTO_UDP, protocol)

    # Deleting the SA causes the first socket to return errors again.
    self.xfrm.DeleteSaInfo(self.GetRemoteAddress(xfrm_version), TEST_SPI,
                           IPPROTO_ESP)
    self.assertRaisesErrno(
        EAGAIN,
        s.sendto, net_test.UDP_PAYLOAD, (remotesockaddr, 53))

    # Clear the socket policy and expect a cleartext packet.
    xfrm_base.SetPolicySockopt(s, family, None)
    s.sendto(net_test.UDP_PAYLOAD, (remotesockaddr, 53))
    self.ExpectPacketOn(netid, "Send after clear, expected %s" % desc, pkt)

    # Clearing the policy twice is safe.
    xfrm_base.SetPolicySockopt(s, family, None)
    s.sendto(net_test.UDP_PAYLOAD, (remotesockaddr, 53))
    self.ExpectPacketOn(netid, "Send after clear 2, expected %s" % desc, pkt)

    # Clearing if a policy was never set is safe.
    s = socket(AF_INET6, SOCK_DGRAM, 0)
    xfrm_base.SetPolicySockopt(s, family, None)

  def testSocketPolicyIPv4(self):
    self._TestSocketPolicy(4)

  def testSocketPolicyIPv6(self):
    self._TestSocketPolicy(6)

  def testSocketPolicyMapped(self):
    self._TestSocketPolicy(5)

  # Sets up sockets and marks to correct netid
  def _SetupUdpEncapSockets(self):
    netid = self.RandomNetid()
    myaddr = self.MyAddress(4, netid)
    remoteaddr = self.GetRemoteAddress(4)

    # Reserve a port on which to receive UDP encapsulated packets. Sending
    # packets works without this (and potentially can send packets with a source
    # port belonging to another application), but receiving requires the port to
    # be bound and the encapsulation socket option enabled.
    encap_sock = net_test.Socket(AF_INET, SOCK_DGRAM, 0)
    encap_sock.bind((myaddr, 0))
    encap_port = encap_sock.getsockname()[1]
    encap_sock.setsockopt(IPPROTO_UDP, xfrm.UDP_ENCAP, xfrm.UDP_ENCAP_ESPINUDP)

    # Open a socket to send traffic.
    s = socket(AF_INET, SOCK_DGRAM, 0)
    self.SelectInterface(s, netid, "mark")
    s.connect((remoteaddr, 53))

    return netid, myaddr, remoteaddr, encap_sock, encap_port, s

  # Sets up SAs and applies socket policy to given socket
  def _SetupUdpEncapSaPair(self, myaddr, remoteaddr, in_spi, out_spi,
                           encap_port, s, use_null_auth):
    in_reqid = 123
    out_reqid = 456

    # Create inbound and outbound SAs that specify UDP encapsulation.
    encaptmpl = xfrm.XfrmEncapTmpl((xfrm.UDP_ENCAP_ESPINUDP, htons(encap_port),
                                    htons(4500), 16 * "\x00"))
    self.CreateNewSa(myaddr, remoteaddr, out_spi, out_reqid, encaptmpl,
                     use_null_auth)

    # Add an encap template that's the mirror of the outbound one.
    encaptmpl.sport, encaptmpl.dport = encaptmpl.dport, encaptmpl.sport
    self.CreateNewSa(remoteaddr, myaddr, in_spi, in_reqid, encaptmpl,
                     use_null_auth)

    # Apply socket policies to s.
    xfrm_base.ApplySocketPolicy(s, AF_INET, xfrm.XFRM_POLICY_OUT, out_spi,
                                out_reqid, None)

    # TODO: why does this work without a per-socket policy applied?
    # The received  packet obviously matches an SA, but don't inbound packets
    # need to match a policy as well? (b/71541609)
    xfrm_base.ApplySocketPolicy(s, AF_INET, xfrm.XFRM_POLICY_IN, in_spi,
                                in_reqid, None)

    # Uncomment for debugging.
    # subprocess.call("ip xfrm state".split())

  # Check that packets can be sent and received.
  def _VerifyUdpEncapSocket(self, netid, remoteaddr, myaddr, encap_port, sock,
                           in_spi, out_spi, null_auth, seq_num):
    # Now send a packet.
    sock.sendto(net_test.UDP_PAYLOAD, (remoteaddr, 53))
    srcport = sock.getsockname()[1]

    # Expect to see an UDP encapsulated packet.
    pkts = self.ReadAllPacketsOn(netid)
    self.assertEquals(1, len(pkts))
    packet = pkts[0]

    auth_algo = (
        xfrm_base._ALGO_AUTH_NULL if null_auth else xfrm_base._ALGO_HMAC_SHA1)
    expected_len = xfrm_base.GetEspPacketLength(
        xfrm.XFRM_MODE_TRANSPORT, 4, True, net_test.UDP_PAYLOAD, auth_algo,
        xfrm_base._ALGO_CBC_AES_256)
    self.assertIsUdpEncapEsp(packet, out_spi, seq_num, expected_len)

    # Now test the receive path. Because we don't know how to decrypt packets,
    # we just play back the encrypted packet that kernel sent earlier. We swap
    # the addresses in the IP header to make the packet look like it's bound for
    # us, but we can't do that for the port numbers because the UDP header is
    # part of the integrity protected payload, which we can only replay as is.
    # So the source and destination ports are swapped and the packet appears to
    # be sent from srcport to port 53. Open another socket on that port, and
    # apply the inbound policy to it.
    twisted_socket = socket(AF_INET, SOCK_DGRAM, 0)
    csocket.SetSocketTimeout(twisted_socket, 100)
    twisted_socket.bind(("0.0.0.0", 53))

    # Save the payload of the packet so we can replay it back to ourselves, and
    # replace the SPI with our inbound SPI.
    payload = str(packet.payload)[8:]
    spi_seq = xfrm.EspHdr((in_spi, seq_num)).Pack()
    payload = spi_seq + payload[len(spi_seq):]

    sainfo = self.xfrm.FindSaInfo(in_spi)
    start_integrity_failures = sainfo.stats.integrity_failed

    # Now play back the valid packet and check that we receive it.
    incoming = (scapy.IP(src=remoteaddr, dst=myaddr) /
                scapy.UDP(sport=4500, dport=encap_port) / payload)
    incoming = scapy.IP(str(incoming))
    self.ReceivePacketOn(netid, incoming)

    sainfo = self.xfrm.FindSaInfo(in_spi)

    # TODO: break this out into a separate test
    # If our SPIs are different, and we aren't using null authentication,
    # we expect the packet to be dropped. We also expect that the integrity
    # failure counter to increase, as SPIs are part of the authenticated or
    # integrity-verified portion of the packet.
    if not null_auth and in_spi != out_spi:
      self.assertRaisesErrno(EAGAIN, twisted_socket.recv, 4096)
      self.assertEquals(start_integrity_failures + 1,
                        sainfo.stats.integrity_failed)
    else:
      data, src = twisted_socket.recvfrom(4096)
      self.assertEquals(net_test.UDP_PAYLOAD, data)
      self.assertEquals((remoteaddr, srcport), src)
      self.assertEquals(start_integrity_failures, sainfo.stats.integrity_failed)

    # Check that unencrypted packets on twisted_socket are not received.
    unencrypted = (
        scapy.IP(src=remoteaddr, dst=myaddr) / scapy.UDP(
            sport=srcport, dport=53) / net_test.UDP_PAYLOAD)
    self.assertRaisesErrno(EAGAIN, twisted_socket.recv, 4096)

  def _RunEncapSocketPolicyTest(self, in_spi, out_spi, use_null_auth):
    netid, myaddr, remoteaddr, encap_sock, encap_port, s = \
        self._SetupUdpEncapSockets()

    self._SetupUdpEncapSaPair(myaddr, remoteaddr, in_spi, out_spi, encap_port,
                              s, use_null_auth)

    # Check that UDP encap sockets work with socket policy and given SAs
    self._VerifyUdpEncapSocket(netid, remoteaddr, myaddr, encap_port, s, in_spi,
                               out_spi, use_null_auth, 1)

  # TODO: Add tests for ESP (non-encap) sockets.
  def testUdpEncapSameSpisNullAuth(self):
    # Use the same SPI both inbound and outbound because this lets us receive
    # encrypted packets by simply replaying the packets the kernel sends
    # without having to disable authentication
    self._RunEncapSocketPolicyTest(TEST_SPI, TEST_SPI, True)

  def testUdpEncapSameSpis(self):
    self._RunEncapSocketPolicyTest(TEST_SPI, TEST_SPI, False)

  def testUdpEncapDifferentSpisNullAuth(self):
    self._RunEncapSocketPolicyTest(TEST_SPI, TEST_SPI2, True)

  def testUdpEncapDifferentSpis(self):
    self._RunEncapSocketPolicyTest(TEST_SPI, TEST_SPI2, False)

  def testUdpEncapRekey(self):
    # Select the two SPIs that will be used
    start_spi = TEST_SPI
    rekey_spi = TEST_SPI2

    # Setup sockets
    netid, myaddr, remoteaddr, encap_sock, encap_port, s = \
        self._SetupUdpEncapSockets()

    # The SAs must use null authentication, since we change SPIs on the fly
    # Without null authentication, this would result in an ESP authentication
    # error since the SPI is part of the authenticated section. The packet
    # would then be dropped
    self._SetupUdpEncapSaPair(myaddr, remoteaddr, start_spi, start_spi,
                              encap_port, s, True)

    # Check that UDP encap sockets work with socket policy and given SAs
    self._VerifyUdpEncapSocket(netid, remoteaddr, myaddr, encap_port, s,
                               start_spi, start_spi, True, 1)

    # Rekey this socket using the make-before-break paradigm. First we create
    # new SAs, update the per-socket policies, and only then remove the old SAs
    #
    # This allows us to switch to the new SA without breaking the outbound path.
    self._SetupUdpEncapSaPair(myaddr, remoteaddr, rekey_spi, rekey_spi,
                              encap_port, s, True)

    # Check that UDP encap socket works with updated socket policy, sending
    # using new SA, but receiving on both old and new SAs
    self._VerifyUdpEncapSocket(netid, remoteaddr, myaddr, encap_port, s,
                               rekey_spi, rekey_spi, True, 1)
    self._VerifyUdpEncapSocket(netid, remoteaddr, myaddr, encap_port, s,
                               start_spi, rekey_spi, True, 2)

    # Delete old SAs
    self.xfrm.DeleteSaInfo(remoteaddr, start_spi, IPPROTO_ESP)
    self.xfrm.DeleteSaInfo(myaddr, start_spi, IPPROTO_ESP)

    # Check that UDP encap socket works with updated socket policy and new SAs
    self._VerifyUdpEncapSocket(netid, remoteaddr, myaddr, encap_port, s,
                               rekey_spi, rekey_spi, True, 3)

  def testAllocSpecificSpi(self):
    spi = 0xABCD
    new_sa = self.xfrm.AllocSpi("::", IPPROTO_ESP, spi, spi)
    self.assertEquals(spi, new_sa.id.spi)

  def testAllocSpecificSpiUnavailable(self):
    """Attempt to allocate the same SPI twice."""
    spi = 0xABCD
    new_sa = self.xfrm.AllocSpi("::", IPPROTO_ESP, spi, spi)
    self.assertEquals(spi, new_sa.id.spi)
    with self.assertRaisesErrno(ENOENT):
      new_sa = self.xfrm.AllocSpi("::", IPPROTO_ESP, spi, spi)

  def testAllocRangeSpi(self):
    start, end = 0xABCD0, 0xABCDF
    new_sa = self.xfrm.AllocSpi("::", IPPROTO_ESP, start, end)
    spi = new_sa.id.spi
    self.assertGreaterEqual(spi, start)
    self.assertLessEqual(spi, end)

  def testAllocRangeSpiUnavailable(self):
    """Attempt to allocate N+1 SPIs from a range of size N."""
    start, end = 0xABCD0, 0xABCDF
    range_size = end - start + 1
    spis = set()
    # Assert that allocating SPI fails when none are available.
    with self.assertRaisesErrno(ENOENT):
      # Allocating range_size + 1 SPIs is guaranteed to fail.  Due to the way
      # kernel picks random SPIs, this has a high probability of failing before
      # reaching that limit.
      for i in xrange(range_size + 1):
        new_sa = self.xfrm.AllocSpi("::", IPPROTO_ESP, start, end)
        spi = new_sa.id.spi
        self.assertNotIn(spi, spis)
        spis.add(spi)

  def testSocketPolicyDstCacheV6(self):
    self._TestSocketPolicyDstCache(6)

  def testSocketPolicyDstCacheV4(self):
    self._TestSocketPolicyDstCache(4)

  def _TestSocketPolicyDstCache(self, version):
    """Test that destination cache is cleared with socket policy.

    This relies on the fact that connect() on a UDP socket populates the
    destination cache.
    """

    # Create UDP socket.
    family = net_test.GetAddressFamily(version)
    netid = self.RandomNetid()
    s = socket(family, SOCK_DGRAM, 0)
    self.SelectInterface(s, netid, "mark")

    # Populate the socket's destination cache.
    remote = self.GetRemoteAddress(version)
    s.connect((remote, 53))

    # Apply a policy to the socket. Should clear dst cache.
    reqid = 123
    xfrm_base.ApplySocketPolicy(s, family, xfrm.XFRM_POLICY_OUT,
                                TEST_SPI, reqid, None)

    # Policy with no matching SA should result in EAGAIN. If destination cache
    # failed to clear, then the UDP packet will be sent normally.
    with self.assertRaisesErrno(EAGAIN):
      s.send(net_test.UDP_PAYLOAD)
    self.ExpectNoPacketsOn(netid, "Packet not blocked by policy")

  def _CheckNullEncryptionTunnelMode(self, version):
    family = net_test.GetAddressFamily(version)
    netid = self.RandomNetid()
    local_addr = self.MyAddress(version, netid)
    remote_addr = self.GetRemoteAddress(version)

    # Borrow the address of another netId as the source address of the tunnel
    tun_local = self.MyAddress(version, self.RandomNetid(netid))
    # For generality, pick a tunnel endpoint that's not the address we
    # connect the socket to.
    tun_remote = TUNNEL_ENDPOINTS[version]

    # Output
    self.xfrm.AddSaInfo(
        tun_local, tun_remote, 0xABCD, xfrm.XFRM_MODE_TUNNEL, 123,
        xfrm_base._ALGO_CRYPT_NULL, xfrm_base._ALGO_AUTH_NULL,
        None, None, None, netid)
    # Input
    self.xfrm.AddSaInfo(
        tun_remote, tun_local, 0x9876, xfrm.XFRM_MODE_TUNNEL, 456,
        xfrm_base._ALGO_CRYPT_NULL, xfrm_base._ALGO_AUTH_NULL,
        None, None, None, None)

    sock = net_test.UDPSocket(family)
    self.SelectInterface(sock, netid, "mark")
    sock.bind((local_addr, 0))
    local_port = sock.getsockname()[1]
    remote_port = 5555

    xfrm_base.ApplySocketPolicy(
        sock, family, xfrm.XFRM_POLICY_OUT, 0xABCD, 123,
        (tun_local, tun_remote))
    xfrm_base.ApplySocketPolicy(
        sock, family, xfrm.XFRM_POLICY_IN, 0x9876, 456,
        (tun_remote, tun_local))

    # Create and receive an ESP packet.
    IpType = {4: scapy.IP, 6: scapy.IPv6}[version]
    input_pkt = (IpType(src=remote_addr, dst=local_addr) /
                 scapy.UDP(sport=remote_port, dport=local_port) /
                 "input hello")
    input_pkt = IpType(str(input_pkt)) # Compute length, checksum.
    input_pkt = xfrm_base.EncryptPacketWithNull(input_pkt, 0x9876,
                                                1, (tun_remote, tun_local))

    self.ReceivePacketOn(netid, input_pkt)
    msg, addr = sock.recvfrom(1024)
    self.assertEquals("input hello", msg)
    self.assertEquals((remote_addr, remote_port), addr[:2])

    # Send and capture a packet.
    sock.sendto("output hello", (remote_addr, remote_port))
    packets = self.ReadAllPacketsOn(netid)
    self.assertEquals(1, len(packets))
    output_pkt = packets[0]
    output_pkt, esp_hdr = xfrm_base.DecryptPacketWithNull(output_pkt)
    self.assertEquals(output_pkt[scapy.UDP].len, len("output_hello") + 8)
    self.assertEquals(remote_addr, output_pkt.dst)
    self.assertEquals(remote_port, output_pkt[scapy.UDP].dport)
    # length of the payload plus the UDP header
    self.assertEquals("output hello", str(output_pkt[scapy.UDP].payload))
    self.assertEquals(0xABCD, esp_hdr.spi)

  def testNullEncryptionTunnelMode(self):
    """Verify null encryption in tunnel mode.

    This test verifies both manual assembly and disassembly of UDP packets
    with ESP in IPsec tunnel mode.
    """
    for version in [4, 6]:
      self._CheckNullEncryptionTunnelMode(version)

  def _CheckNullEncryptionTransportMode(self, version):
    family = net_test.GetAddressFamily(version)
    netid = self.RandomNetid()
    local_addr = self.MyAddress(version, netid)
    remote_addr = self.GetRemoteAddress(version)

    # Output
    self.xfrm.AddSaInfo(
        local_addr, remote_addr, 0xABCD, xfrm.XFRM_MODE_TRANSPORT, 123,
        xfrm_base._ALGO_CRYPT_NULL, xfrm_base._ALGO_AUTH_NULL,
        None, None, None, None)
    # Input
    self.xfrm.AddSaInfo(
        remote_addr, local_addr, 0x9876, xfrm.XFRM_MODE_TRANSPORT, 456,
        xfrm_base._ALGO_CRYPT_NULL, xfrm_base._ALGO_AUTH_NULL,
        None, None, None, None)

    sock = net_test.UDPSocket(family)
    self.SelectInterface(sock, netid, "mark")
    sock.bind((local_addr, 0))
    local_port = sock.getsockname()[1]
    remote_port = 5555

    xfrm_base.ApplySocketPolicy(
        sock, family, xfrm.XFRM_POLICY_OUT, 0xABCD, 123, None)
    xfrm_base.ApplySocketPolicy(
        sock, family, xfrm.XFRM_POLICY_IN, 0x9876, 456, None)

    # Create and receive an ESP packet.
    IpType = {4: scapy.IP, 6: scapy.IPv6}[version]
    input_pkt = (IpType(src=remote_addr, dst=local_addr) /
                 scapy.UDP(sport=remote_port, dport=local_port) /
                 "input hello")
    input_pkt = IpType(str(input_pkt)) # Compute length, checksum.
    input_pkt = xfrm_base.EncryptPacketWithNull(input_pkt, 0x9876, 1, None)

    self.ReceivePacketOn(netid, input_pkt)
    msg, addr = sock.recvfrom(1024)
    self.assertEquals("input hello", msg)
    self.assertEquals((remote_addr, remote_port), addr[:2])

    # Send and capture a packet.
    sock.sendto("output hello", (remote_addr, remote_port))
    packets = self.ReadAllPacketsOn(netid)
    self.assertEquals(1, len(packets))
    output_pkt = packets[0]
    output_pkt, esp_hdr = xfrm_base.DecryptPacketWithNull(output_pkt)
    # length of the payload plus the UDP header
    self.assertEquals(output_pkt[scapy.UDP].len, len("output_hello") + 8)
    self.assertEquals(remote_addr, output_pkt.dst)
    self.assertEquals(remote_port, output_pkt[scapy.UDP].dport)
    self.assertEquals("output hello", str(output_pkt[scapy.UDP].payload))
    self.assertEquals(0xABCD, esp_hdr.spi)

  def testNullEncryptionTransportMode(self):
    """Verify null encryption in transport mode.

    This test verifies both manual assembly and disassembly of UDP packets
    with ESP in IPsec transport mode.
    """
    for version in [4, 6]:
      self._CheckNullEncryptionTransportMode(version)

  def _CheckGlobalPoliciesByMark(self, version):
    """Tests that global policies may differ by only the mark."""
    family = net_test.GetAddressFamily(version)
    sel = xfrm.EmptySelector(family)
    # Pick 2 arbitrary mark values.
    mark1 = xfrm.XfrmMark(mark=0xf00, mask=xfrm_base.MARK_MASK_ALL)
    mark2 = xfrm.XfrmMark(mark=0xf00d, mask=xfrm_base.MARK_MASK_ALL)
    # Create a global policy.
    policy = xfrm.UserPolicy(xfrm.XFRM_POLICY_OUT, sel)
    tmpl = xfrm.UserTemplate(AF_UNSPEC, 0xfeed, 0, None)
    # Create the policy with the first mark.
    self.xfrm.AddPolicyInfo(policy, tmpl, mark1)
    # Create the same policy but with the second (different) mark.
    self.xfrm.AddPolicyInfo(policy, tmpl, mark2)
    # Delete the policies individually
    self.xfrm.DeletePolicyInfo(sel, xfrm.XFRM_POLICY_OUT, mark1)
    self.xfrm.DeletePolicyInfo(sel, xfrm.XFRM_POLICY_OUT, mark2)

  def testGlobalPoliciesByMarkV4(self):
    self._CheckGlobalPoliciesByMark(4)

  def testGlobalPoliciesByMarkV6(self):
    self._CheckGlobalPoliciesByMark(6)

  def _CheckUpdatePolicy(self, version):
    """Tests that we can can update the template on a policy."""
    family = net_test.GetAddressFamily(version)
    tmpl1 = xfrm.UserTemplate(family, 0xdead, 0, None)
    tmpl2 = xfrm.UserTemplate(family, 0xbeef, 0, None)
    sel = xfrm.EmptySelector(family)
    policy = xfrm.UserPolicy(xfrm.XFRM_POLICY_OUT, sel)
    mark = xfrm.XfrmMark(mark=0xf00, mask=xfrm_base.MARK_MASK_ALL)

    def _CheckTemplateMatch(tmpl):
      """Dump the SPD and match a single template on a single policy."""
      dump = self.xfrm.DumpPolicyInfo()
      self.assertEquals(1, len(dump))
      _, attributes = dump[0]
      self.assertEquals(attributes['XFRMA_TMPL'], tmpl)

    # Create a new policy using update.
    self.xfrm.UpdatePolicyInfo(policy, tmpl1, mark, None)
    # NEWPOLICY will not update the existing policy. This checks both that
    # UPDPOLICY created a policy and that NEWPOLICY will not perform updates.
    _CheckTemplateMatch(tmpl1)
    with self.assertRaisesErrno(EEXIST):
      self.xfrm.AddPolicyInfo(policy, tmpl2, mark, None)
    # Update the policy using UPDPOLICY.
    self.xfrm.UpdatePolicyInfo(policy, tmpl2, mark, None)
    # There should only be one policy after update, and it should have the
    # updated template.
    _CheckTemplateMatch(tmpl2)

  def testUpdatePolicyV4(self):
    self._CheckUpdatePolicy(4)

  def testUpdatePolicyV6(self):
    self._CheckUpdatePolicy(6)

  def _CheckPolicyDifferByDirection(self,version):
    """Tests that policies can differ only by direction."""
    family = net_test.GetAddressFamily(version)
    tmpl = xfrm.UserTemplate(family, 0xdead, 0, None)
    sel = xfrm.EmptySelector(family)
    mark = xfrm.XfrmMark(mark=0xf00, mask=xfrm_base.MARK_MASK_ALL)
    policy = xfrm.UserPolicy(xfrm.XFRM_POLICY_OUT, sel)
    self.xfrm.AddPolicyInfo(policy, tmpl, mark)
    policy = xfrm.UserPolicy(xfrm.XFRM_POLICY_IN, sel)
    self.xfrm.AddPolicyInfo(policy, tmpl, mark)

  def testPolicyDifferByDirectionV4(self):
    self._CheckPolicyDifferByDirection(4)

  def testPolicyDifferByDirectionV6(self):
    self._CheckPolicyDifferByDirection(6)

class XfrmOutputMarkTest(xfrm_base.XfrmLazyTest):

  def _CheckTunnelModeOutputMark(self, version, tunsrc, mark, expected_netid):
    """Tests sending UDP packets to tunnel mode SAs with output marks.

    Opens a UDP socket and binds it to a random netid, then sets up tunnel mode
    SAs with an output_mark of mark and sets a socket policy to use the SA.
    Then checks that sending on those SAs sends a packet on expected_netid,
    or, if expected_netid is zero, checks that sending returns ENETUNREACH.

    Args:
      version: 4 or 6.
      tunsrc: A string, the source address of the tunnel.
      mark: An integer, the output_mark to set in the SA.
      expected_netid: An integer, the netid to expect the kernel to send the
          packet on. If None, expect that sendto will fail with ENETUNREACH.
    """
    # Open a UDP socket and bind it to a random netid.
    family = net_test.GetAddressFamily(version)
    s = socket(family, SOCK_DGRAM, 0)
    self.SelectInterface(s, self.RandomNetid(), "mark")

    # For generality, pick a tunnel endpoint that's not the address we
    # connect the socket to.
    tundst = TUNNEL_ENDPOINTS[version]
    tun_addrs = (tunsrc, tundst)

    # Create a tunnel mode SA and use XFRM_OUTPUT_MARK to bind it to netid.
    spi = TEST_SPI * mark
    reqid = 100 + spi
    self.xfrm.AddSaInfo(tunsrc, tundst, spi, xfrm.XFRM_MODE_TUNNEL, reqid,
                        xfrm_base._ALGO_CBC_AES_256, xfrm_base._ALGO_HMAC_SHA1,
                        None, None, None, mark)

    # Set a socket policy to use it.
    xfrm_base.ApplySocketPolicy(s, family, xfrm.XFRM_POLICY_OUT, spi, reqid,
                                tun_addrs)

    # Send a packet and check that we see it on the wire.
    remoteaddr = self.GetRemoteAddress(version)

    packetlen = xfrm_base.GetEspPacketLength(xfrm.XFRM_MODE_TUNNEL, version,
                                             False, net_test.UDP_PAYLOAD,
                                             xfrm_base._ALGO_HMAC_SHA1,
                                             xfrm_base._ALGO_CBC_AES_256)

    if expected_netid is not None:
      s.sendto(net_test.UDP_PAYLOAD, (remoteaddr, 53))
      self._ExpectEspPacketOn(expected_netid, spi, 1, packetlen, tunsrc, tundst)
    else:
      with self.assertRaisesErrno(ENETUNREACH):
        s.sendto(net_test.UDP_PAYLOAD, (remoteaddr, 53))

  def testTunnelModeOutputMarkIPv4(self):
    for netid in self.NETIDS:
      tunsrc = self.MyAddress(4, netid)
      self._CheckTunnelModeOutputMark(4, tunsrc, netid, netid)

  def testTunnelModeOutputMarkIPv6(self):
    for netid in self.NETIDS:
      tunsrc = self.MyAddress(6, netid)
      self._CheckTunnelModeOutputMark(6, tunsrc, netid, netid)

  def testTunnelModeOutputNoMarkIPv4(self):
    tunsrc = self.MyAddress(4, self.RandomNetid())
    self._CheckTunnelModeOutputMark(4, tunsrc, 0, None)

  def testTunnelModeOutputNoMarkIPv6(self):
    tunsrc = self.MyAddress(6, self.RandomNetid())
    self._CheckTunnelModeOutputMark(6, tunsrc, 0, None)

  def testTunnelModeOutputInvalidMarkIPv4(self):
    tunsrc = self.MyAddress(4, self.RandomNetid())
    self._CheckTunnelModeOutputMark(4, tunsrc, 9999, None)

  def testTunnelModeOutputInvalidMarkIPv6(self):
    tunsrc = self.MyAddress(6, self.RandomNetid())
    self._CheckTunnelModeOutputMark(6, tunsrc, 9999, None)

  def testTunnelModeOutputMarkAttributes(self):
    mark = 1234567
    self.xfrm.AddSaInfo(TEST_ADDR1, TUNNEL_ENDPOINTS[6], 0x1234,
                        xfrm.XFRM_MODE_TUNNEL, 100, xfrm_base._ALGO_CBC_AES_256,
                        xfrm_base._ALGO_HMAC_SHA1, None, None, None, mark)
    dump = self.xfrm.DumpSaInfo()
    self.assertEquals(1, len(dump))
    sainfo, attributes = dump[0]
    self.assertEquals(mark, attributes["XFRMA_OUTPUT_MARK"])

  def testInvalidAlgorithms(self):
    key = "af442892cdcd0ef650e9c299f9a8436a".decode("hex")
    invalid_auth = (xfrm.XfrmAlgoAuth(("invalid(algo)", 128, 96)), key)
    invalid_crypt = (xfrm.XfrmAlgo(("invalid(algo)", 128)), key)
    with self.assertRaisesErrno(ENOSYS):
        self.xfrm.AddSaInfo(TEST_ADDR1, TEST_ADDR2, 0x1234,
            xfrm.XFRM_MODE_TRANSPORT, 0, xfrm_base._ALGO_CBC_AES_256,
            invalid_auth, None, None, None, 0)
    with self.assertRaisesErrno(ENOSYS):
        self.xfrm.AddSaInfo(TEST_ADDR1, TEST_ADDR2, 0x1234,
            xfrm.XFRM_MODE_TRANSPORT, 0, invalid_crypt,
            xfrm_base._ALGO_HMAC_SHA1, None, None, None, 0)

  def testUpdateSaAddMark(self):
    """Test that an embryonic SA can be updated to add a mark."""
    for version in [4, 6]:
      spi = 0xABCD
      # Test that an SA created with ALLOCSPI can be updated with the mark.
      new_sa = self.xfrm.AllocSpi(net_test.GetWildcardAddress(version),
                                  IPPROTO_ESP, spi, spi)
      mark = xfrm.ExactMatchMark(0xf00d)
      self.xfrm.AddSaInfo(net_test.GetWildcardAddress(version),
                          net_test.GetWildcardAddress(version),
                          spi, xfrm.XFRM_MODE_TUNNEL, 0,
                          xfrm_base._ALGO_CBC_AES_256,
                          xfrm_base._ALGO_HMAC_SHA1,
                          None, None, mark, 0, is_update=True)
      dump = self.xfrm.DumpSaInfo()
      self.assertEquals(1, len(dump)) # check that update updated
      sainfo, attributes = dump[0]
      self.assertEquals(mark, attributes["XFRMA_MARK"])
      self.xfrm.DeleteSaInfo(net_test.GetWildcardAddress(version),
                             spi, IPPROTO_ESP, mark)

  def getXfrmStat(self, statName):
    stateVal = 0
    with open(XFRM_STATS_PROCFILE, 'r') as f:
      for line in f:
          if statName in line:
            stateVal = int(line.split()[1])
            break
      f.close()
    return stateVal

  def testUpdateActiveSaMarks(self):
    """Test that the OUTPUT_MARK can be updated on an ACTIVE SA."""
    for version in [4, 6]:
      family = net_test.GetAddressFamily(version)
      netid = self.RandomNetid()
      remote = self.GetRemoteAddress(version)
      local = self.MyAddress(version, netid)
      s = socket(family, SOCK_DGRAM, 0)
      self.SelectInterface(s, netid, "mark")
      # Create a mark that we will apply to the policy and later the SA
      mark = xfrm.ExactMatchMark(netid)

      # Create a global policy that selects using the mark.
      sel = xfrm.EmptySelector(family)
      policy = xfrm.UserPolicy(xfrm.XFRM_POLICY_OUT, sel)
      tmpl = xfrm.UserTemplate(family, 0, 0, (local, remote))
      self.xfrm.AddPolicyInfo(policy, tmpl, mark)

      # Pull /proc/net/xfrm_stats for baseline
      outNoStateCount = self.getXfrmStat(XFRM_STATS_OUT_NO_STATES);

      # should increment XfrmOutNoStates
      s.sendto(net_test.UDP_PAYLOAD, (remote, 53))

      # Check to make sure XfrmOutNoStates is incremented by exactly 1
      self.assertEquals(outNoStateCount + 1,
                        self.getXfrmStat(XFRM_STATS_OUT_NO_STATES))

      length = xfrm_base.GetEspPacketLength(xfrm.XFRM_MODE_TUNNEL,
                                            version, False,
                                            net_test.UDP_PAYLOAD,
                                            xfrm_base._ALGO_HMAC_SHA1,
                                            xfrm_base._ALGO_CBC_AES_256)

      # Add a default SA with no mark that routes to nowhere.
      self.xfrm.AddSaInfo(local,
                          remote,
                          TEST_SPI, xfrm.XFRM_MODE_TUNNEL, 0,
                          xfrm_base._ALGO_CBC_AES_256,
                          xfrm_base._ALGO_HMAC_SHA1,
                          None, None, None, 0, is_update=False)
      self.assertRaisesErrno(
          ENETUNREACH,
          s.sendto, net_test.UDP_PAYLOAD, (remote, 53))

      # Update the SA to route to a valid netid.
      self.xfrm.AddSaInfo(local,
                          remote,
                          TEST_SPI, xfrm.XFRM_MODE_TUNNEL, 0,
                          xfrm_base._ALGO_CBC_AES_256,
                          xfrm_base._ALGO_HMAC_SHA1,
                          None, None, None, netid, is_update=True)

      # Now the payload routes to the updated netid.
      s.sendto(net_test.UDP_PAYLOAD, (remote, 53))
      self._ExpectEspPacketOn(netid, TEST_SPI, 1, length, None, None)

      # Get a new netid and reroute the packets to the new netid.
      reroute_netid = self.RandomNetid(netid)
      # Update the SA to change the output mark.
      self.xfrm.AddSaInfo(local,
                         remote,
                         TEST_SPI, xfrm.XFRM_MODE_TUNNEL, 0,
                         xfrm_base._ALGO_CBC_AES_256,
                         xfrm_base._ALGO_HMAC_SHA1,
                         None, None, None, reroute_netid, is_update=True)

      s.sendto(net_test.UDP_PAYLOAD, (remote, 53))
      self._ExpectEspPacketOn(reroute_netid, TEST_SPI, 2, length, None, None)

      dump = self.xfrm.DumpSaInfo()

      self.assertEquals(1, len(dump)) # check that update updated
      sainfo, attributes = dump[0]
      self.assertEquals(reroute_netid, attributes["XFRMA_OUTPUT_MARK"])

      self.xfrm.DeleteSaInfo(remote, TEST_SPI, IPPROTO_ESP, None)
      self.xfrm.DeletePolicyInfo(sel, xfrm.XFRM_POLICY_OUT, mark)

if __name__ == "__main__":
  unittest.main()
