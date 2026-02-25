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
from socket import *  # pylint: disable=wildcard-import

import random
import itertools
import struct
import unittest

from scapy import all as scapy
from tun_twister import TunTwister
import csocket
import iproute
import multinetwork_base
import net_test
import packets
import util
import xfrm
import xfrm_base

_LOOPBACK_IFINDEX = 1
_TEST_XFRM_IFNAME = "ipsec42"
_TEST_XFRM_IF_ID = 42

# Does the kernel support xfrmi interfaces?
def HaveXfrmInterfaces():
  try:
    i = iproute.IPRoute()
    i.CreateXfrmInterface(_TEST_XFRM_IFNAME, _TEST_XFRM_IF_ID,
                          _LOOPBACK_IFINDEX)
    i.DeleteLink(_TEST_XFRM_IFNAME)
    try:
      i.GetIfIndex(_TEST_XFRM_IFNAME)
      assert "Deleted interface %s still exists!" % _TEST_XFRM_IFNAME
    except IOError:
      pass
    return True
  except IOError:
    return False

HAVE_XFRM_INTERFACES = HaveXfrmInterfaces()

# Parameters to setup tunnels as special networks
_TUNNEL_NETID_OFFSET = 0xFC00  # Matches reserved netid range for IpSecService
_BASE_TUNNEL_NETID = {4: 40, 6: 60}
_BASE_VTI_OKEY = 2000000100
_BASE_VTI_IKEY = 2000000200

_TEST_OUT_SPI = 0x1234
_TEST_IN_SPI = _TEST_OUT_SPI

_TEST_OKEY = 2000000100
_TEST_IKEY = 2000000200

_TEST_REMOTE_PORT = 1234

_SCAPY_IP_TYPE = {4: scapy.IP, 6: scapy.IPv6}


def _GetLocalInnerAddress(version):
  return {4: "10.16.5.15", 6: "2001:db8:1::1"}[version]


def _GetRemoteInnerAddress(version):
  return {4: "10.16.5.20", 6: "2001:db8:2::1"}[version]


def _GetRemoteOuterAddress(version):
  return {4: net_test.IPV4_ADDR, 6: net_test.IPV6_ADDR}[version]


def _GetNullAuthCryptTunnelModePkt(inner_version, src_inner, src_outer,
                                   src_port, dst_inner, dst_outer,
                                   dst_port, spi, seq_num, ip_hdr_options=None):
  if ip_hdr_options is None:
    ip_hdr_options = {}

  ip_hdr_options.update({'src': src_inner, 'dst': dst_inner})

  # Build and receive an ESP packet destined for the inner socket
  IpType = {4: scapy.IP, 6: scapy.IPv6}[inner_version]
  input_pkt = (
      IpType(**ip_hdr_options) / scapy.UDP(sport=src_port, dport=dst_port) /
      net_test.UDP_PAYLOAD)
  input_pkt = IpType(str(input_pkt))  # Compute length, checksum.
  input_pkt = xfrm_base.EncryptPacketWithNull(input_pkt, spi, seq_num,
                                              (src_outer, dst_outer))

  return input_pkt


def _CreateReceiveSock(version, port=0):
  # Create a socket to receive packets.
  read_sock = socket(net_test.GetAddressFamily(version), SOCK_DGRAM, 0)
  read_sock.bind((net_test.GetWildcardAddress(version), port))
  # The second parameter of the tuple is the port number regardless of AF.
  local_port = read_sock.getsockname()[1]
  # Guard against the eventuality of the receive failing.
  csocket.SetSocketTimeout(read_sock, 500)

  return read_sock, local_port


def _SendPacket(testInstance, netid, version, remote, remote_port):
  # Send a packet out via the tunnel-backed network, bound for the port number
  # of the input socket.
  write_sock = socket(net_test.GetAddressFamily(version), SOCK_DGRAM, 0)
  testInstance.SelectInterface(write_sock, netid, "mark")
  write_sock.sendto(net_test.UDP_PAYLOAD, (remote, remote_port))
  local_port = write_sock.getsockname()[1]

  return local_port


def InjectTests():
  InjectParameterizedTests(XfrmTunnelTest)
  InjectParameterizedTests(XfrmInterfaceTest)
  InjectParameterizedTests(XfrmVtiTest)


def InjectParameterizedTests(cls):
  VERSIONS = (4, 6)
  param_list = itertools.product(VERSIONS, VERSIONS)

  def NameGenerator(*args):
    return "IPv%d_in_IPv%d" % tuple(args)

  util.InjectParameterizedTest(cls, param_list, NameGenerator)


class XfrmTunnelTest(xfrm_base.XfrmLazyTest):

  def _CheckTunnelOutput(self, inner_version, outer_version, underlying_netid,
                         netid, local_inner, remote_inner, local_outer,
                         remote_outer, write_sock):

    write_sock.sendto(net_test.UDP_PAYLOAD, (remote_inner, 53))
    self._ExpectEspPacketOn(underlying_netid, _TEST_OUT_SPI, 1, None,
                            local_outer, remote_outer)

  def _CheckTunnelInput(self, inner_version, outer_version, underlying_netid,
                        netid, local_inner, remote_inner, local_outer,
                        remote_outer, read_sock):

    # The second parameter of the tuple is the port number regardless of AF.
    local_port = read_sock.getsockname()[1]

    # Build and receive an ESP packet destined for the inner socket
    input_pkt = _GetNullAuthCryptTunnelModePkt(
        inner_version, remote_inner, remote_outer, _TEST_REMOTE_PORT,
        local_inner, local_outer, local_port, _TEST_IN_SPI, 1)
    self.ReceivePacketOn(underlying_netid, input_pkt)

    # Verify that the packet data and src are correct
    data, src = read_sock.recvfrom(4096)
    self.assertEquals(net_test.UDP_PAYLOAD, data)
    self.assertEquals((remote_inner, _TEST_REMOTE_PORT), src[:2])

  def _TestTunnel(self, inner_version, outer_version, func, direction,
                  test_output_mark_unset):
    """Test a unidirectional XFRM Tunnel with explicit selectors"""
    # Select the underlying netid, which represents the external
    # interface from/to which to route ESP packets.
    u_netid = self.RandomNetid()
    # Select a random netid that will originate traffic locally and
    # which represents the netid on which the plaintext is sent
    netid = self.RandomNetid(exclude=u_netid)

    local_inner = self.MyAddress(inner_version, netid)
    remote_inner = _GetRemoteInnerAddress(inner_version)
    local_outer = self.MyAddress(outer_version, u_netid)
    remote_outer = _GetRemoteOuterAddress(outer_version)

    output_mark = u_netid
    if test_output_mark_unset:
      output_mark = None
      self.SetDefaultNetwork(u_netid)

    try:
      # Create input/ouput SPs, SAs and sockets to simulate a more realistic
      # environment.
      self.xfrm.CreateTunnel(
          xfrm.XFRM_POLICY_IN, xfrm.SrcDstSelector(remote_inner, local_inner),
          remote_outer, local_outer, _TEST_IN_SPI, xfrm_base._ALGO_CRYPT_NULL,
          xfrm_base._ALGO_AUTH_NULL, None, None, None, xfrm.MATCH_METHOD_ALL)

      self.xfrm.CreateTunnel(
          xfrm.XFRM_POLICY_OUT, xfrm.SrcDstSelector(local_inner, remote_inner),
          local_outer, remote_outer, _TEST_OUT_SPI, xfrm_base._ALGO_CBC_AES_256,
          xfrm_base._ALGO_HMAC_SHA1, None, output_mark, None, xfrm.MATCH_METHOD_ALL)

      write_sock = socket(net_test.GetAddressFamily(inner_version), SOCK_DGRAM, 0)
      self.SelectInterface(write_sock, netid, "mark")
      read_sock, _ = _CreateReceiveSock(inner_version)

      sock = write_sock if direction == xfrm.XFRM_POLICY_OUT else read_sock
      func(inner_version, outer_version, u_netid, netid, local_inner,
          remote_inner, local_outer, remote_outer, sock)
    finally:
      if test_output_mark_unset:
        self.ClearDefaultNetwork()

  def ParamTestTunnelInput(self, inner_version, outer_version):
    self._TestTunnel(inner_version, outer_version, self._CheckTunnelInput,
                     xfrm.XFRM_POLICY_IN, False)

  def ParamTestTunnelOutput(self, inner_version, outer_version):
    self._TestTunnel(inner_version, outer_version, self._CheckTunnelOutput,
                     xfrm.XFRM_POLICY_OUT, False)

  def ParamTestTunnelOutputNoSetMark(self, inner_version, outer_version):
    self._TestTunnel(inner_version, outer_version, self._CheckTunnelOutput,
                     xfrm.XFRM_POLICY_OUT, True)


@unittest.skipUnless(net_test.LINUX_VERSION >= (3, 18, 0), "VTI Unsupported")
class XfrmAddDeleteVtiTest(xfrm_base.XfrmBaseTest):
  def _VerifyVtiInfoData(self, vti_info_data, version, local_addr, remote_addr,
                         ikey, okey):
    self.assertEquals(vti_info_data["IFLA_VTI_IKEY"], ikey)
    self.assertEquals(vti_info_data["IFLA_VTI_OKEY"], okey)

    family = AF_INET if version == 4 else AF_INET6
    self.assertEquals(inet_ntop(family, vti_info_data["IFLA_VTI_LOCAL"]),
                      local_addr)
    self.assertEquals(inet_ntop(family, vti_info_data["IFLA_VTI_REMOTE"]),
                      remote_addr)

  def testAddVti(self):
    """Test the creation of a Virtual Tunnel Interface."""
    for version in [4, 6]:
      netid = self.RandomNetid()
      local_addr = self.MyAddress(version, netid)
      self.iproute.CreateVirtualTunnelInterface(
          dev_name=_TEST_XFRM_IFNAME,
          local_addr=local_addr,
          remote_addr=_GetRemoteOuterAddress(version),
          o_key=_TEST_OKEY,
          i_key=_TEST_IKEY)
      self._VerifyVtiInfoData(
          self.iproute.GetIfinfoData(_TEST_XFRM_IFNAME), version, local_addr,
          _GetRemoteOuterAddress(version), _TEST_IKEY, _TEST_OKEY)

      new_remote_addr = {4: net_test.IPV4_ADDR2, 6: net_test.IPV6_ADDR2}
      new_okey = _TEST_OKEY + _TEST_XFRM_IF_ID
      new_ikey = _TEST_IKEY + _TEST_XFRM_IF_ID
      self.iproute.CreateVirtualTunnelInterface(
          dev_name=_TEST_XFRM_IFNAME,
          local_addr=local_addr,
          remote_addr=new_remote_addr[version],
          o_key=new_okey,
          i_key=new_ikey,
          is_update=True)

      self._VerifyVtiInfoData(
          self.iproute.GetIfinfoData(_TEST_XFRM_IFNAME), version, local_addr,
          new_remote_addr[version], new_ikey, new_okey)

      if_index = self.iproute.GetIfIndex(_TEST_XFRM_IFNAME)

      # Validate that the netlink interface matches the ioctl interface.
      self.assertEquals(net_test.GetInterfaceIndex(_TEST_XFRM_IFNAME), if_index)
      self.iproute.DeleteLink(_TEST_XFRM_IFNAME)
      with self.assertRaises(IOError):
        self.iproute.GetIfIndex(_TEST_XFRM_IFNAME)

  def _QuietDeleteLink(self, ifname):
    try:
      self.iproute.DeleteLink(ifname)
    except IOError:
      # The link was not present.
      pass

  def tearDown(self):
    super(XfrmAddDeleteVtiTest, self).tearDown()
    self._QuietDeleteLink(_TEST_XFRM_IFNAME)


class SaInfo(object):

  def __init__(self, spi):
    self.spi = spi
    self.seq_num = 1


class IpSecBaseInterface(object):

  def __init__(self, iface, netid, underlying_netid, local, remote, version):
    self.iface = iface
    self.netid = netid
    self.underlying_netid = underlying_netid
    self.local, self.remote = local, remote

    # XFRM interfaces technically do not have a version. This keeps track of
    # the IP version of the local and remote addresses.
    self.version = version
    self.rx = self.tx = 0
    self.addrs = {}

    self.iproute = iproute.IPRoute()
    self.xfrm = xfrm.Xfrm()

  def Teardown(self):
    self.TeardownXfrm()
    self.TeardownInterface()

  def TeardownInterface(self):
    self.iproute.DeleteLink(self.iface)

  def SetupXfrm(self, use_null_crypt):
    rand_spi = random.randint(0, 0x7fffffff)
    self.in_sa = SaInfo(rand_spi)
    self.out_sa = SaInfo(rand_spi)

    # Select algorithms:
    if use_null_crypt:
      auth, crypt = xfrm_base._ALGO_AUTH_NULL, xfrm_base._ALGO_CRYPT_NULL
    else:
      auth, crypt = xfrm_base._ALGO_HMAC_SHA1, xfrm_base._ALGO_CBC_AES_256

    self._SetupXfrmByType(auth, crypt)

  def Rekey(self, outer_family, new_out_sa, new_in_sa):
    """Rekeys the Tunnel Interface

    Creates new SAs and updates the outbound security policy to use new SAs.

    Args:
      outer_family: AF_INET or AF_INET6
      new_out_sa: An SaInfo struct representing the new outbound SA's info
      new_in_sa: An SaInfo struct representing the new inbound SA's info
    """
    self._Rekey(outer_family, new_out_sa, new_in_sa)

    # Update Interface object
    self.out_sa = new_out_sa
    self.in_sa = new_in_sa

  def TeardownXfrm(self):
    raise NotImplementedError("Subclasses should implement this")

  def _SetupXfrmByType(self, auth_algo, crypt_algo):
    raise NotImplementedError("Subclasses should implement this")

  def _Rekey(self, outer_family, new_out_sa, new_in_sa):
    raise NotImplementedError("Subclasses should implement this")


class VtiInterface(IpSecBaseInterface):

  def __init__(self, iface, netid, underlying_netid, _, local, remote, version):
    super(VtiInterface, self).__init__(iface, netid, underlying_netid, local,
                                       remote, version)

    self.ikey = _TEST_IKEY + netid
    self.okey = _TEST_OKEY + netid

    self.SetupInterface()
    self.SetupXfrm(False)

  def SetupInterface(self):
    return self.iproute.CreateVirtualTunnelInterface(
        self.iface, self.local, self.remote, self.ikey, self.okey)

  def _SetupXfrmByType(self, auth_algo, crypt_algo):
    # For the VTI, the selectors are wildcard since packets will only
    # be selected if they have the appropriate mark, hence the inner
    # addresses are wildcard.
    self.xfrm.CreateTunnel(xfrm.XFRM_POLICY_OUT, None, self.local, self.remote,
                           self.out_sa.spi, crypt_algo, auth_algo,
                           xfrm.ExactMatchMark(self.okey),
                           self.underlying_netid, None, xfrm.MATCH_METHOD_ALL)

    self.xfrm.CreateTunnel(xfrm.XFRM_POLICY_IN, None, self.remote, self.local,
                           self.in_sa.spi, crypt_algo, auth_algo,
                           xfrm.ExactMatchMark(self.ikey), None, None,
                           xfrm.MATCH_METHOD_MARK)

  def TeardownXfrm(self):
    self.xfrm.DeleteTunnel(xfrm.XFRM_POLICY_OUT, None, self.remote,
                           self.out_sa.spi, self.okey, None)
    self.xfrm.DeleteTunnel(xfrm.XFRM_POLICY_IN, None, self.local,
                           self.in_sa.spi, self.ikey, None)

  def _Rekey(self, outer_family, new_out_sa, new_in_sa):
    # TODO: Consider ways to share code with xfrm.CreateTunnel(). It's mostly
    #       the same, but rekeys are asymmetric, and only update the outbound
    #       policy.
    self.xfrm.AddSaInfo(self.local, self.remote, new_out_sa.spi,
                        xfrm.XFRM_MODE_TUNNEL, 0, xfrm_base._ALGO_CRYPT_NULL,
                        xfrm_base._ALGO_AUTH_NULL, None, None,
                        xfrm.ExactMatchMark(self.okey), self.underlying_netid)

    self.xfrm.AddSaInfo(self.remote, self.local, new_in_sa.spi,
                        xfrm.XFRM_MODE_TUNNEL, 0, xfrm_base._ALGO_CRYPT_NULL,
                        xfrm_base._ALGO_AUTH_NULL, None, None,
                        xfrm.ExactMatchMark(self.ikey), None)

    # Create new policies for IPv4 and IPv6.
    for sel in [xfrm.EmptySelector(AF_INET), xfrm.EmptySelector(AF_INET6)]:
      # Add SPI-specific output policy to enforce using new outbound SPI
      policy = xfrm.UserPolicy(xfrm.XFRM_POLICY_OUT, sel)
      tmpl = xfrm.UserTemplate(outer_family, new_out_sa.spi, 0,
                                    (self.local, self.remote))
      self.xfrm.UpdatePolicyInfo(policy, tmpl, xfrm.ExactMatchMark(self.okey),
                                 0)

  def DeleteOldSaInfo(self, outer_family, old_in_spi, old_out_spi):
    self.xfrm.DeleteSaInfo(self.local, old_in_spi, IPPROTO_ESP,
                           xfrm.ExactMatchMark(self.ikey))
    self.xfrm.DeleteSaInfo(self.remote, old_out_spi, IPPROTO_ESP,
                           xfrm.ExactMatchMark(self.okey))


@unittest.skipUnless(HAVE_XFRM_INTERFACES, "XFRM interfaces unsupported")
class XfrmAddDeleteXfrmInterfaceTest(xfrm_base.XfrmBaseTest):
  """Test the creation of an XFRM Interface."""

  def testAddXfrmInterface(self):
    self.iproute.CreateXfrmInterface(_TEST_XFRM_IFNAME, _TEST_XFRM_IF_ID,
                                     _LOOPBACK_IFINDEX)
    if_index = self.iproute.GetIfIndex(_TEST_XFRM_IFNAME)
    net_test.SetInterfaceUp(_TEST_XFRM_IFNAME)

    # Validate that the netlink interface matches the ioctl interface.
    self.assertEquals(net_test.GetInterfaceIndex(_TEST_XFRM_IFNAME), if_index)
    self.iproute.DeleteLink(_TEST_XFRM_IFNAME)
    with self.assertRaises(IOError):
      self.iproute.GetIfIndex(_TEST_XFRM_IFNAME)


class XfrmInterface(IpSecBaseInterface):

  def __init__(self, iface, netid, underlying_netid, ifindex, local, remote,
               version):
    super(XfrmInterface, self).__init__(iface, netid, underlying_netid, local,
                                        remote, version)

    self.ifindex = ifindex
    self.xfrm_if_id = netid

    self.SetupInterface()
    self.SetupXfrm(False)

  def SetupInterface(self):
    """Create an XFRM interface."""
    return self.iproute.CreateXfrmInterface(self.iface, self.netid, self.ifindex)

  def _SetupXfrmByType(self, auth_algo, crypt_algo):
    self.xfrm.CreateTunnel(xfrm.XFRM_POLICY_OUT, None, self.local, self.remote,
                           self.out_sa.spi, crypt_algo, auth_algo, None,
                           self.underlying_netid, self.xfrm_if_id,
                           xfrm.MATCH_METHOD_ALL)
    self.xfrm.CreateTunnel(xfrm.XFRM_POLICY_IN, None, self.remote, self.local,
                           self.in_sa.spi, crypt_algo, auth_algo, None, None,
                           self.xfrm_if_id, xfrm.MATCH_METHOD_IFID)

  def TeardownXfrm(self):
    self.xfrm.DeleteTunnel(xfrm.XFRM_POLICY_OUT, None, self.remote,
                           self.out_sa.spi, None, self.xfrm_if_id)
    self.xfrm.DeleteTunnel(xfrm.XFRM_POLICY_IN, None, self.local,
                           self.in_sa.spi, None, self.xfrm_if_id)

  def _Rekey(self, outer_family, new_out_sa, new_in_sa):
    # TODO: Consider ways to share code with xfrm.CreateTunnel(). It's mostly
    #       the same, but rekeys are asymmetric, and only update the outbound
    #       policy.
    self.xfrm.AddSaInfo(
        self.local, self.remote, new_out_sa.spi, xfrm.XFRM_MODE_TUNNEL, 0,
        xfrm_base._ALGO_CRYPT_NULL, xfrm_base._ALGO_AUTH_NULL, None, None,
        None, self.underlying_netid, xfrm_if_id=self.xfrm_if_id)

    self.xfrm.AddSaInfo(
        self.remote, self.local, new_in_sa.spi, xfrm.XFRM_MODE_TUNNEL, 0,
        xfrm_base._ALGO_CRYPT_NULL, xfrm_base._ALGO_AUTH_NULL, None, None,
        None, None, xfrm_if_id=self.xfrm_if_id)

    # Create new policies for IPv4 and IPv6.
    for sel in [xfrm.EmptySelector(AF_INET), xfrm.EmptySelector(AF_INET6)]:
      # Add SPI-specific output policy to enforce using new outbound SPI
      policy = xfrm.UserPolicy(xfrm.XFRM_POLICY_OUT, sel)
      tmpl = xfrm.UserTemplate(outer_family, new_out_sa.spi, 0,
                                    (self.local, self.remote))
      self.xfrm.UpdatePolicyInfo(policy, tmpl, None, self.xfrm_if_id)

  def DeleteOldSaInfo(self, outer_family, old_in_spi, old_out_spi):
    self.xfrm.DeleteSaInfo(self.local, old_in_spi, IPPROTO_ESP, None,
                           self.xfrm_if_id)
    self.xfrm.DeleteSaInfo(self.remote, old_out_spi, IPPROTO_ESP, None,
                           self.xfrm_if_id)


class XfrmTunnelBase(xfrm_base.XfrmBaseTest):

  @classmethod
  def setUpClass(cls):
    xfrm_base.XfrmBaseTest.setUpClass()
    # Tunnel interfaces use marks extensively, so configure realistic packet
    # marking rules to make the test representative, make PMTUD work, etc.
    cls.SetInboundMarks(True)
    cls.SetMarkReflectSysctls(1)

    # Group by tunnel version to ensure that we test at least one IPv4 and one
    # IPv6 tunnel
    cls.tunnelsV4 = {}
    cls.tunnelsV6 = {}
    for i, underlying_netid in enumerate(cls.tuns):
      for version in 4, 6:
        netid = _BASE_TUNNEL_NETID[version] + _TUNNEL_NETID_OFFSET + i
        iface = "ipsec%s" % netid
        local = cls.MyAddress(version, underlying_netid)
        if version == 4:
          remote = (net_test.IPV4_ADDR if (i % 2) else net_test.IPV4_ADDR2)
        else:
          remote = (net_test.IPV6_ADDR if (i % 2) else net_test.IPV6_ADDR2)

        ifindex = cls.ifindices[underlying_netid]
        tunnel = cls.INTERFACE_CLASS(iface, netid, underlying_netid, ifindex,
                                   local, remote, version)
        cls._SetInboundMarking(netid, iface, True)
        cls._SetupTunnelNetwork(tunnel, True)

        if version == 4:
          cls.tunnelsV4[netid] = tunnel
        else:
          cls.tunnelsV6[netid] = tunnel

  @classmethod
  def tearDownClass(cls):
    # The sysctls are restored by MultinetworkBaseTest.tearDownClass.
    cls.SetInboundMarks(False)
    for tunnel in cls.tunnelsV4.values() + cls.tunnelsV6.values():
      cls._SetInboundMarking(tunnel.netid, tunnel.iface, False)
      cls._SetupTunnelNetwork(tunnel, False)
      tunnel.Teardown()
    xfrm_base.XfrmBaseTest.tearDownClass()

  def randomTunnel(self, outer_version):
    version_dict = self.tunnelsV4 if outer_version == 4 else self.tunnelsV6
    return random.choice(version_dict.values())

  def setUp(self):
    multinetwork_base.MultiNetworkBaseTest.setUp(self)
    self.iproute = iproute.IPRoute()
    self.xfrm = xfrm.Xfrm()

  def tearDown(self):
    multinetwork_base.MultiNetworkBaseTest.tearDown(self)

  def _SwapInterfaceAddress(self, ifname, old_addr, new_addr):
    """Exchange two addresses on a given interface.

    Args:
      ifname: Name of the interface
      old_addr: An address to be removed from the interface
      new_addr: An address to be added to an interface
    """
    version = 6 if ":" in new_addr else 4
    ifindex = net_test.GetInterfaceIndex(ifname)
    self.iproute.AddAddress(new_addr,
                            net_test.AddressLengthBits(version), ifindex)
    self.iproute.DelAddress(old_addr,
                            net_test.AddressLengthBits(version), ifindex)

  @classmethod
  def _GetLocalAddress(cls, version, netid):
    if version == 4:
      return cls._MyIPv4Address(netid - _TUNNEL_NETID_OFFSET)
    else:
      return cls.OnlinkPrefix(6, netid - _TUNNEL_NETID_OFFSET) + "1"

  @classmethod
  def _SetupTunnelNetwork(cls, tunnel, is_add):
    """Setup rules and routes for a tunnel Network.

    Takes an interface and depending on the boolean
    value of is_add, either adds or removes the rules
    and routes for a tunnel interface to behave like an
    Android Network for purposes of testing.

    Args:
      tunnel: A VtiInterface or XfrmInterface, the tunnel to set up.
      is_add: Boolean that causes this method to perform setup if True or
        teardown if False
    """
    if is_add:
      # Disable router solicitations to avoid occasional spurious packets
      # arriving on the underlying network; there are two possible behaviors
      # when that occurred: either only the RA packet is read, and when it
      # is echoed back to the tunnel, it causes the test to fail by not
      # receiving # the UDP_PAYLOAD; or, two packets may arrive on the
      # underlying # network which fails the assertion that only one ESP packet
      # is received.
      cls.SetSysctl(
          "/proc/sys/net/ipv6/conf/%s/router_solicitations" % tunnel.iface, 0)
      net_test.SetInterfaceUp(tunnel.iface)

    for version in [4, 6]:
      ifindex = net_test.GetInterfaceIndex(tunnel.iface)
      table = tunnel.netid

      # Set up routing rules.
      start, end = cls.UidRangeForNetid(tunnel.netid)
      cls.iproute.UidRangeRule(version, is_add, start, end, table,
                                cls.PRIORITY_UID)
      cls.iproute.OifRule(version, is_add, tunnel.iface, table, cls.PRIORITY_OIF)
      cls.iproute.FwmarkRule(version, is_add, tunnel.netid, cls.NETID_FWMASK,
                              table, cls.PRIORITY_FWMARK)

      # Configure IP addresses.
      addr = cls._GetLocalAddress(version, tunnel.netid)
      prefixlen = net_test.AddressLengthBits(version)
      tunnel.addrs[version] = addr
      if is_add:
        cls.iproute.AddAddress(addr, prefixlen, ifindex)
        cls.iproute.AddRoute(version, table, "default", 0, None, ifindex)
      else:
        cls.iproute.DelRoute(version, table, "default", 0, None, ifindex)
        cls.iproute.DelAddress(addr, prefixlen, ifindex)

  def assertReceivedPacket(self, tunnel, sa_info):
    tunnel.rx += 1
    self.assertEquals((tunnel.rx, tunnel.tx),
                      self.iproute.GetRxTxPackets(tunnel.iface))
    sa_info.seq_num += 1

  def assertSentPacket(self, tunnel, sa_info):
    tunnel.tx += 1
    self.assertEquals((tunnel.rx, tunnel.tx),
                      self.iproute.GetRxTxPackets(tunnel.iface))
    sa_info.seq_num += 1

  def _CheckTunnelInput(self, tunnel, inner_version, local_inner, remote_inner,
                        sa_info=None, expect_fail=False):
    """Test null-crypt input path over an IPsec interface."""
    if sa_info is None:
      sa_info = tunnel.in_sa
    read_sock, local_port = _CreateReceiveSock(inner_version)

    input_pkt = _GetNullAuthCryptTunnelModePkt(
        inner_version, remote_inner, tunnel.remote, _TEST_REMOTE_PORT,
        local_inner, tunnel.local, local_port, sa_info.spi, sa_info.seq_num)
    self.ReceivePacketOn(tunnel.underlying_netid, input_pkt)

    if expect_fail:
      self.assertRaisesErrno(EAGAIN, read_sock.recv, 4096)
    else:
      # Verify that the packet data and src are correct
      data, src = read_sock.recvfrom(4096)
      self.assertReceivedPacket(tunnel, sa_info)
      self.assertEquals(net_test.UDP_PAYLOAD, data)
      self.assertEquals((remote_inner, _TEST_REMOTE_PORT), src[:2])

  def _CheckTunnelOutput(self, tunnel, inner_version, local_inner,
                         remote_inner, sa_info=None):
    """Test null-crypt output path over an IPsec interface."""
    if sa_info is None:
      sa_info = tunnel.out_sa
    local_port = _SendPacket(self, tunnel.netid, inner_version, remote_inner,
                             _TEST_REMOTE_PORT)

    # Read a tunneled IP packet on the underlying (outbound) network
    # verifying that it is an ESP packet.
    pkt = self._ExpectEspPacketOn(tunnel.underlying_netid, sa_info.spi,
                                  sa_info.seq_num, None, tunnel.local,
                                  tunnel.remote)

    # Get and update the IP headers on the inner payload so that we can do a simple
    # comparison of byte data. Unfortunately, due to the scapy version this runs on,
    # we cannot parse past the ESP header to the inner IP header, and thus have to
    # workaround in this manner
    if inner_version == 4:
      ip_hdr_options = {
        'id': scapy.IP(str(pkt.payload)[8:]).id,
        'flags': scapy.IP(str(pkt.payload)[8:]).flags
      }
    else:
      ip_hdr_options = {'fl': scapy.IPv6(str(pkt.payload)[8:]).fl}

    expected = _GetNullAuthCryptTunnelModePkt(
        inner_version, local_inner, tunnel.local, local_port, remote_inner,
        tunnel.remote, _TEST_REMOTE_PORT, sa_info.spi, sa_info.seq_num,
        ip_hdr_options)

    # Check outer header manually (Avoids having to overwrite outer header's
    # id, flags or flow label)
    self.assertSentPacket(tunnel, sa_info)
    self.assertEquals(expected.src, pkt.src)
    self.assertEquals(expected.dst, pkt.dst)
    self.assertEquals(len(expected), len(pkt))

    # Check everything else
    self.assertEquals(str(expected.payload), str(pkt.payload))

  def _CheckTunnelEncryption(self, tunnel, inner_version, local_inner,
                             remote_inner):
    """Test both input and output paths over an encrypted IPsec interface.

    This tests specifically makes sure that the both encryption and decryption
    work together, as opposed to the _CheckTunnel(Input|Output) where the
    input and output paths are tested separately, and using null encryption.
    """
    src_port = _SendPacket(self, tunnel.netid, inner_version, remote_inner,
                           _TEST_REMOTE_PORT)

    # Make sure it appeared on the underlying interface
    pkt = self._ExpectEspPacketOn(tunnel.underlying_netid, tunnel.out_sa.spi,
                                  tunnel.out_sa.seq_num, None, tunnel.local,
                                  tunnel.remote)

    # Check that packet is not sent in plaintext
    self.assertTrue(str(net_test.UDP_PAYLOAD) not in str(pkt))

    # Check src/dst
    self.assertEquals(tunnel.local, pkt.src)
    self.assertEquals(tunnel.remote, pkt.dst)

    # Check that the interface statistics recorded the outbound packet
    self.assertSentPacket(tunnel, tunnel.out_sa)

    try:
      # Swap the interface addresses to pretend we are the remote
      self._SwapInterfaceAddress(
          tunnel.iface, new_addr=remote_inner, old_addr=local_inner)

      # Swap the packet's IP headers and write it back to the underlying
      # network.
      pkt = TunTwister.TwistPacket(pkt)
      read_sock, local_port = _CreateReceiveSock(inner_version,
                                                 _TEST_REMOTE_PORT)
      self.ReceivePacketOn(tunnel.underlying_netid, pkt)

      # Verify that the packet data and src are correct
      data, src = read_sock.recvfrom(4096)
      self.assertEquals(net_test.UDP_PAYLOAD, data)
      self.assertEquals((local_inner, src_port), src[:2])

      # Check that the interface statistics recorded the inbound packet
      self.assertReceivedPacket(tunnel, tunnel.in_sa)
    finally:
      # Swap the interface addresses to pretend we are the remote
      self._SwapInterfaceAddress(
          tunnel.iface, new_addr=local_inner, old_addr=remote_inner)

  def _CheckTunnelIcmp(self, tunnel, inner_version, local_inner, remote_inner,
                       sa_info=None):
    """Test ICMP error path over an IPsec interface."""
    if sa_info is None:
      sa_info = tunnel.out_sa
    # Now attempt to provoke an ICMP error.
    # TODO: deduplicate with multinetwork_test.py.
    dst_prefix, intermediate = {
        4: ("172.19.", "172.16.9.12"),
        6: ("2001:db8::", "2001:db8::1")
    }[tunnel.version]

    local_port = _SendPacket(self, tunnel.netid, inner_version, remote_inner,
                             _TEST_REMOTE_PORT)
    pkt = self._ExpectEspPacketOn(tunnel.underlying_netid, sa_info.spi,
                                  sa_info.seq_num, None, tunnel.local,
                                  tunnel.remote)
    self.assertSentPacket(tunnel, sa_info)

    myaddr = self.MyAddress(tunnel.version, tunnel.underlying_netid)
    _, toobig = packets.ICMPPacketTooBig(tunnel.version, intermediate, myaddr,
                                         pkt)
    self.ReceivePacketOn(tunnel.underlying_netid, toobig)

    # Check that the packet too big reduced the MTU.
    routes = self.iproute.GetRoutes(tunnel.remote, 0, tunnel.underlying_netid, None)
    self.assertEquals(1, len(routes))
    rtmsg, attributes = routes[0]
    self.assertEquals(iproute.RTN_UNICAST, rtmsg.type)
    self.assertEquals(packets.PTB_MTU, attributes["RTA_METRICS"]["RTAX_MTU"])

    # Clear PMTU information so that future tests don't have to worry about it.
    self.InvalidateDstCache(tunnel.version, tunnel.underlying_netid)

  def _CheckTunnelEncryptionWithIcmp(self, tunnel, inner_version, local_inner,
                                     remote_inner):
    """Test combined encryption path with ICMP errors over an IPsec tunnel"""
    self._CheckTunnelEncryption(tunnel, inner_version, local_inner,
                                remote_inner)
    self._CheckTunnelIcmp(tunnel, inner_version, local_inner, remote_inner)
    self._CheckTunnelEncryption(tunnel, inner_version, local_inner,
                                remote_inner)

  def _TestTunnel(self, inner_version, outer_version, func, use_null_crypt):
    """Bootstrap method to setup and run tests for the given parameters."""
    tunnel = self.randomTunnel(outer_version)

    try:
      # Some tests require that the out_seq_num and in_seq_num are the same
      # (Specifically encrypted tests), rebuild SAs to ensure seq_num is 1
      #
      # Until we get better scapy support, the only way we can build an
      # encrypted packet is to send it out, and read the packet from the wire.
      # We then generally use this as the "inbound" encrypted packet, injecting
      # it into the interface for which it is expected on.
      #
      # As such, this is required to ensure that encrypted packets (which we
      # currently have no way to easily modify) are not considered replay
      # attacks by the inbound SA.  (eg: received 3 packets, seq_num_in = 3,
      # sent only 1, # seq_num_out = 1, inbound SA would consider this a replay
      # attack)
      tunnel.TeardownXfrm()
      tunnel.SetupXfrm(use_null_crypt)

      local_inner = tunnel.addrs[inner_version]
      remote_inner = _GetRemoteInnerAddress(inner_version)

      for i in range(2):
        func(tunnel, inner_version, local_inner, remote_inner)
    finally:
      if use_null_crypt:
        tunnel.TeardownXfrm()
        tunnel.SetupXfrm(False)

  def _CheckTunnelRekey(self, tunnel, inner_version, local_inner, remote_inner):
    old_out_sa = tunnel.out_sa
    old_in_sa = tunnel.in_sa

    # Check to make sure that both directions work before rekey
    self._CheckTunnelInput(tunnel, inner_version, local_inner, remote_inner,
                           old_in_sa)
    self._CheckTunnelOutput(tunnel, inner_version, local_inner, remote_inner,
                            old_out_sa)

    # Rekey
    outer_family = net_test.GetAddressFamily(tunnel.version)

    # Create new SA
    # Distinguish the new SAs with new SPIs.
    new_out_sa = SaInfo(old_out_sa.spi + 1)
    new_in_sa = SaInfo(old_in_sa.spi + 1)

    # Perform Rekey
    tunnel.Rekey(outer_family, new_out_sa, new_in_sa)

    # Expect that the old SPI still works for inbound packets
    self._CheckTunnelInput(tunnel, inner_version, local_inner, remote_inner,
                           old_in_sa)

    # Test both paths with new SPIs, expect outbound to use new SPI
    self._CheckTunnelInput(tunnel, inner_version, local_inner, remote_inner,
                           new_in_sa)
    self._CheckTunnelOutput(tunnel, inner_version, local_inner, remote_inner,
                            new_out_sa)

    # Delete old SAs
    tunnel.DeleteOldSaInfo(outer_family, old_in_sa.spi, old_out_sa.spi)

    # Test both paths with new SPIs; should still work
    self._CheckTunnelInput(tunnel, inner_version, local_inner, remote_inner,
                           new_in_sa)
    self._CheckTunnelOutput(tunnel, inner_version, local_inner, remote_inner,
                            new_out_sa)

    # Expect failure upon trying to receive a packet with the deleted SPI
    self._CheckTunnelInput(tunnel, inner_version, local_inner, remote_inner,
                           old_in_sa, True)

  def _TestTunnelRekey(self, inner_version, outer_version):
    """Test packet input and output over a Virtual Tunnel Interface."""
    tunnel = self.randomTunnel(outer_version)

    try:
      # Always use null_crypt, so we can check input and output separately
      tunnel.TeardownXfrm()
      tunnel.SetupXfrm(True)

      local_inner = tunnel.addrs[inner_version]
      remote_inner = _GetRemoteInnerAddress(inner_version)

      self._CheckTunnelRekey(tunnel, inner_version, local_inner, remote_inner)
    finally:
      tunnel.TeardownXfrm()
      tunnel.SetupXfrm(False)


@unittest.skipUnless(net_test.LINUX_VERSION >= (3, 18, 0), "VTI Unsupported")
class XfrmVtiTest(XfrmTunnelBase):

  INTERFACE_CLASS = VtiInterface

  def ParamTestVtiInput(self, inner_version, outer_version):
    self._TestTunnel(inner_version, outer_version, self._CheckTunnelInput, True)

  def ParamTestVtiOutput(self, inner_version, outer_version):
    self._TestTunnel(inner_version, outer_version, self._CheckTunnelOutput,
                     True)

  def ParamTestVtiInOutEncrypted(self, inner_version, outer_version):
    self._TestTunnel(inner_version, outer_version, self._CheckTunnelEncryption,
                     False)

  def ParamTestVtiIcmp(self, inner_version, outer_version):
    self._TestTunnel(inner_version, outer_version, self._CheckTunnelIcmp, False)

  def ParamTestVtiEncryptionWithIcmp(self, inner_version, outer_version):
    self._TestTunnel(inner_version, outer_version,
                     self._CheckTunnelEncryptionWithIcmp, False)

  def ParamTestVtiRekey(self, inner_version, outer_version):
    self._TestTunnelRekey(inner_version, outer_version)


@unittest.skipUnless(HAVE_XFRM_INTERFACES, "XFRM interfaces unsupported")
class XfrmInterfaceTest(XfrmTunnelBase):

  INTERFACE_CLASS = XfrmInterface

  def ParamTestXfrmIntfInput(self, inner_version, outer_version):
    self._TestTunnel(inner_version, outer_version, self._CheckTunnelInput, True)

  def ParamTestXfrmIntfOutput(self, inner_version, outer_version):
    self._TestTunnel(inner_version, outer_version, self._CheckTunnelOutput,
                     True)

  def ParamTestXfrmIntfInOutEncrypted(self, inner_version, outer_version):
    self._TestTunnel(inner_version, outer_version, self._CheckTunnelEncryption,
                     False)

  def ParamTestXfrmIntfIcmp(self, inner_version, outer_version):
    self._TestTunnel(inner_version, outer_version, self._CheckTunnelIcmp, False)

  def ParamTestXfrmIntfEncryptionWithIcmp(self, inner_version, outer_version):
    self._TestTunnel(inner_version, outer_version,
                     self._CheckTunnelEncryptionWithIcmp, False)

  def ParamTestXfrmIntfRekey(self, inner_version, outer_version):
    self._TestTunnelRekey(inner_version, outer_version)


if __name__ == "__main__":
  InjectTests()
  unittest.main()
