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

"""Partial implementation of xfrm netlink code and socket options."""

# pylint: disable=g-bad-todo

import os
from socket import *  # pylint: disable=wildcard-import
import struct

import net_test
import csocket
import cstruct
import netlink


# Netlink constants. See include/uapi/linux/xfrm.h.
# Message types.
XFRM_MSG_NEWSA = 16
XFRM_MSG_DELSA = 17
XFRM_MSG_GETSA = 18
XFRM_MSG_NEWPOLICY = 19
XFRM_MSG_DELPOLICY = 20
XFRM_MSG_GETPOLICY = 21
XFRM_MSG_ALLOCSPI = 22
XFRM_MSG_ACQUIRE = 23
XFRM_MSG_EXPIRE = 24
XFRM_MSG_UPDPOLICY = 25
XFRM_MSG_UPDSA = 26
XFRM_MSG_POLEXPIRE = 27
XFRM_MSG_FLUSHSA = 28
XFRM_MSG_FLUSHPOLICY = 29
XFRM_MSG_NEWAE = 30
XFRM_MSG_GETAE = 31
XFRM_MSG_REPORT = 32
XFRM_MSG_MIGRATE = 33
XFRM_MSG_NEWSADINFO = 34
XFRM_MSG_GETSADINFO = 35
XFRM_MSG_NEWSPDINFO = 36
XFRM_MSG_GETSPDINFO = 37
XFRM_MSG_MAPPING = 38

# Attributes.
XFRMA_UNSPEC = 0
XFRMA_ALG_AUTH = 1
XFRMA_ALG_CRYPT = 2
XFRMA_ALG_COMP = 3
XFRMA_ENCAP = 4
XFRMA_TMPL = 5
XFRMA_SA = 6
XFRMA_POLICY = 7
XFRMA_SEC_CTX = 8
XFRMA_LTIME_VAL = 9
XFRMA_REPLAY_VAL = 10
XFRMA_REPLAY_THRESH = 11
XFRMA_ETIMER_THRESH = 12
XFRMA_SRCADDR = 13
XFRMA_COADDR = 14
XFRMA_LASTUSED = 15
XFRMA_POLICY_TYPE = 16
XFRMA_MIGRATE = 17
XFRMA_ALG_AEAD = 18
XFRMA_KMADDRESS = 19
XFRMA_ALG_AUTH_TRUNC = 20
XFRMA_MARK = 21
XFRMA_TFCPAD = 22
XFRMA_REPLAY_ESN_VAL = 23
XFRMA_SA_EXTRA_FLAGS = 24
XFRMA_PROTO = 25
XFRMA_ADDRESS_FILTER = 26
XFRMA_PAD = 27
XFRMA_OFFLOAD_DEV = 28
XFRMA_OUTPUT_MARK = 29
XFRMA_INPUT_MARK = 30
XFRMA_IF_ID = 31

# Other netlink constants. See include/uapi/linux/xfrm.h.

# Directions.
XFRM_POLICY_IN = 0
XFRM_POLICY_OUT = 1
XFRM_POLICY_FWD = 2
XFRM_POLICY_MASK = 3

# Policy sharing.
XFRM_SHARE_ANY     = 0  #  /* No limitations */
XFRM_SHARE_SESSION = 1  #  /* For this session only */
XFRM_SHARE_USER    = 2  #  /* For this user only */
XFRM_SHARE_UNIQUE  = 3  #  /* Use once */

# Modes.
XFRM_MODE_TRANSPORT = 0
XFRM_MODE_TUNNEL = 1
XFRM_MODE_ROUTEOPTIMIZATION = 2
XFRM_MODE_IN_TRIGGER = 3
XFRM_MODE_BEET = 4
XFRM_MODE_MAX = 5

# Actions.
XFRM_POLICY_ALLOW = 0
XFRM_POLICY_BLOCK = 1

# Policy flags.
XFRM_POLICY_LOCALOK = 1
XFRM_POLICY_ICMP = 2

# State flags.
XFRM_STATE_AF_UNSPEC = 32

# XFRM algorithm names, as defined in net/xfrm/xfrm_algo.c.
XFRM_EALG_CBC_AES = "cbc(aes)"
XFRM_AALG_HMAC_MD5 = "hmac(md5)"
XFRM_AALG_HMAC_SHA1 = "hmac(sha1)"
XFRM_AALG_HMAC_SHA256 = "hmac(sha256)"
XFRM_AALG_HMAC_SHA384 = "hmac(sha384)"
XFRM_AALG_HMAC_SHA512 = "hmac(sha512)"
XFRM_AEAD_GCM_AES = "rfc4106(gcm(aes))"

# Data structure formats.
# These aren't constants, they're classes. So, pylint: disable=invalid-name
XfrmSelector = cstruct.Struct(
    "XfrmSelector", "=16s16sHHHHHBBBxxxiI",
    "daddr saddr dport dport_mask sport sport_mask "
    "family prefixlen_d prefixlen_s proto ifindex user")

XfrmLifetimeCfg = cstruct.Struct(
    "XfrmLifetimeCfg", "=QQQQQQQQ",
    "soft_byte hard_byte soft_packet hard_packet "
    "soft_add_expires hard_add_expires soft_use_expires hard_use_expires")

XfrmLifetimeCur = cstruct.Struct(
    "XfrmLifetimeCur", "=QQQQ", "bytes packets add_time use_time")

XfrmAlgo = cstruct.Struct("XfrmAlgo", "=64AI", "name key_len")

XfrmAlgoAuth = cstruct.Struct("XfrmAlgoAuth", "=64AII",
                              "name key_len trunc_len")

XfrmAlgoAead = cstruct.Struct("XfrmAlgoAead", "=64AII", "name key_len icv_len")

XfrmStats = cstruct.Struct(
    "XfrmStats", "=III", "replay_window replay integrity_failed")

XfrmId = cstruct.Struct("XfrmId", "!16sIBxxx", "daddr spi proto")

XfrmUserTmpl = cstruct.Struct(
    "XfrmUserTmpl", "=SHxx16sIBBBxIII",
    "id family saddr reqid mode share optional aalgos ealgos calgos",
    [XfrmId])

XfrmEncapTmpl = cstruct.Struct(
    "XfrmEncapTmpl", "=HHHxx16s", "type sport dport oa")

XfrmUsersaInfo = cstruct.Struct(
    "XfrmUsersaInfo", "=SS16sSSSIIHBBB7x",
    "sel id saddr lft curlft stats seq reqid family mode replay_window flags",
    [XfrmSelector, XfrmId, XfrmLifetimeCfg, XfrmLifetimeCur, XfrmStats])

XfrmUserSpiInfo = cstruct.Struct(
    "XfrmUserSpiInfo", "=SII", "info min max", [XfrmUsersaInfo])

# Technically the family is a 16-bit field, but only a few families are in use,
# and if we pretend it's 8 bits (i.e., use "Bx" instead of "H") we can think
# of the whole structure as being in network byte order.
XfrmUsersaId = cstruct.Struct(
    "XfrmUsersaId", "!16sIBxBx", "daddr spi family proto")

# xfrm.h - struct xfrm_userpolicy_info
XfrmUserpolicyInfo = cstruct.Struct(
    "XfrmUserpolicyInfo", "=SSSIIBBBBxxxx",
    "sel lft curlft priority index dir action flags share",
    [XfrmSelector, XfrmLifetimeCfg, XfrmLifetimeCur])

XfrmUserpolicyId = cstruct.Struct(
        "XfrmUserpolicyId", "=SIBxxx", "sel index dir", [XfrmSelector])

XfrmUsersaFlush = cstruct.Struct("XfrmUsersaFlush", "=B", "proto")

XfrmMark = cstruct.Struct("XfrmMark", "=II", "mark mask")

# Socket options. See include/uapi/linux/in.h.
IP_IPSEC_POLICY = 16
IP_XFRM_POLICY = 17
IPV6_IPSEC_POLICY = 34
IPV6_XFRM_POLICY = 35

# UDP encapsulation constants. See include/uapi/linux/udp.h.
UDP_ENCAP = 100
UDP_ENCAP_ESPINUDP_NON_IKE = 1
UDP_ENCAP_ESPINUDP = 2

_INF = 2 ** 64 -1
NO_LIFETIME_CFG = XfrmLifetimeCfg((_INF, _INF, _INF, _INF, 0, 0, 0, 0))
NO_LIFETIME_CUR = "\x00" * len(XfrmLifetimeCur)

# IPsec constants.
IPSEC_PROTO_ANY = 255

# ESP header, not technically XFRM but we need a place for a protocol
# header and this is the only one we have.
# TODO: move this somewhere more appropriate when possible
EspHdr = cstruct.Struct("EspHdr", "!II", "spi seqnum")

# Local constants.
_DEFAULT_REPLAY_WINDOW = 4
ALL_ALGORITHMS = 0xffffffff

# Policy-SA match method (for VTI/XFRM-I).
MATCH_METHOD_ALL = "all"
MATCH_METHOD_MARK = "mark"
MATCH_METHOD_IFID = "ifid"


def RawAddress(addr):
  """Converts an IP address string to binary format."""
  family = AF_INET6 if ":" in addr else AF_INET
  return inet_pton(family, addr)


def PaddedAddress(addr):
  """Converts an IP address string to binary format for InetDiagSockId."""
  padded = RawAddress(addr)
  if len(padded) < 16:
    padded += "\x00" * (16 - len(padded))
  return padded


XFRM_ADDR_ANY = PaddedAddress("::")


def EmptySelector(family):
  """A selector that matches all packets of the specified address family."""
  return XfrmSelector(family=family)


def SrcDstSelector(src, dst):
  """A selector that matches packets between the specified IP addresses."""
  srcver = csocket.AddressVersion(src)
  dstver = csocket.AddressVersion(dst)
  if srcver != dstver:
    raise ValueError("Cross-address family selector specified: %s -> %s" %
                     (src, dst))
  prefixlen = net_test.AddressLengthBits(srcver)
  family = net_test.GetAddressFamily(srcver)
  return XfrmSelector(saddr=PaddedAddress(src), daddr=PaddedAddress(dst),
      prefixlen_s=prefixlen, prefixlen_d=prefixlen, family=family)


def UserPolicy(direction, selector):
  """Create an IPsec policy.

  Args:
    direction: XFRM_POLICY_IN or XFRM_POLICY_OUT
    selector: An XfrmSelector, the packets to transform.

  Return: a XfrmUserpolicyInfo cstruct.
  """
  # Create a user policy that specifies that all packets in the specified
  # direction matching the selector should be encrypted.
  return XfrmUserpolicyInfo(
      sel=selector,
      lft=NO_LIFETIME_CFG,
      curlft=NO_LIFETIME_CUR,
      dir=direction,
      action=XFRM_POLICY_ALLOW,
      flags=XFRM_POLICY_LOCALOK,
      share=XFRM_SHARE_UNIQUE)


def UserTemplate(family, spi, reqid, tun_addrs):
  """Create an ESP policy and template.

  Args:
    spi: 32-bit SPI in host byte order
    reqid: 32-bit ID matched against SAs
    tun_addrs: A tuple of (local, remote) addresses for tunnel mode, or None
      to request a transport mode SA.

  Return: a tuple of XfrmUserpolicyInfo, XfrmUserTmpl
  """
  # For transport mode, set template source and destination are empty.
  # For tunnel mode, explicitly specify source and destination addresses.
  if tun_addrs is None:
    mode = XFRM_MODE_TRANSPORT
    saddr = XFRM_ADDR_ANY
    daddr = XFRM_ADDR_ANY
  else:
    mode = XFRM_MODE_TUNNEL
    saddr = PaddedAddress(tun_addrs[0])
    daddr = PaddedAddress(tun_addrs[1])

  # Create a template that specifies the SPI and the protocol.
  xfrmid = XfrmId(daddr=daddr, spi=spi, proto=IPPROTO_ESP)
  template = XfrmUserTmpl(
      id=xfrmid,
      family=family,
      saddr=saddr,
      reqid=reqid,
      mode=mode,
      share=XFRM_SHARE_UNIQUE,
      optional=0,  #require
      aalgos=ALL_ALGORITHMS,
      ealgos=ALL_ALGORITHMS,
      calgos=ALL_ALGORITHMS)

  return template


def ExactMatchMark(mark):
  """An XfrmMark that matches only the specified mark."""
  return XfrmMark((mark, 0xffffffff))


class Xfrm(netlink.NetlinkSocket):
  """Netlink interface to xfrm."""

  DEBUG = False

  def __init__(self):
    super(Xfrm, self).__init__(netlink.NETLINK_XFRM)

  def _GetConstantName(self, value, prefix):
    return super(Xfrm, self)._GetConstantName(__name__, value, prefix)

  def MaybeDebugCommand(self, command, flags, data):
    if "ALL" not in self.NL_DEBUG and "XFRM" not in self.NL_DEBUG:
      return

    if command == XFRM_MSG_GETSA:
      if flags & netlink.NLM_F_DUMP:
        struct_type = XfrmUsersaInfo
      else:
        struct_type = XfrmUsersaId
    elif command == XFRM_MSG_DELSA:
      struct_type = XfrmUsersaId
    elif command == XFRM_MSG_ALLOCSPI:
      struct_type = XfrmUserSpiInfo
    elif command == XFRM_MSG_NEWPOLICY:
      struct_type = XfrmUserpolicyInfo
    else:
      struct_type = None

    cmdname = self._GetConstantName(command, "XFRM_MSG_")
    if struct_type:
      print "%s %s" % (cmdname, str(self._ParseNLMsg(data, struct_type)))
    else:
      print "%s" % cmdname

  def _Decode(self, command, unused_msg, nla_type, nla_data):
    """Decodes netlink attributes to Python types."""
    name = self._GetConstantName(nla_type, "XFRMA_")

    if name in ["XFRMA_ALG_CRYPT", "XFRMA_ALG_AUTH"]:
      data = cstruct.Read(nla_data, XfrmAlgo)[0]
    elif name == "XFRMA_ALG_AUTH_TRUNC":
      data = cstruct.Read(nla_data, XfrmAlgoAuth)[0]
    elif name == "XFRMA_ENCAP":
      data = cstruct.Read(nla_data, XfrmEncapTmpl)[0]
    elif name == "XFRMA_MARK":
      data = cstruct.Read(nla_data, XfrmMark)[0]
    elif name == "XFRMA_OUTPUT_MARK":
      data = struct.unpack("=I", nla_data)[0]
    elif name == "XFRMA_TMPL":
      data = cstruct.Read(nla_data, XfrmUserTmpl)[0]
    elif name == "XFRMA_IF_ID":
      data = struct.unpack("=I", nla_data)[0]
    else:
      data = nla_data

    return name, data

  def _UpdatePolicyInfo(self, msg, policy, tmpl, mark, xfrm_if_id):
    """Send a policy to the Security Policy Database"""
    nlattrs = []
    if tmpl is not None:
      nlattrs.append((XFRMA_TMPL, tmpl))
    if mark is not None:
      nlattrs.append((XFRMA_MARK, mark))
    if xfrm_if_id is not None:
      nlattrs.append((XFRMA_IF_ID, struct.pack("=I", xfrm_if_id)))
    self.SendXfrmNlRequest(msg, policy, nlattrs)

  def AddPolicyInfo(self, policy, tmpl, mark, xfrm_if_id=None):
    """Add a new policy to the Security Policy Database

    If the policy exists, then return an error (EEXIST).

    Args:
      policy: an unpacked XfrmUserpolicyInfo
      tmpl: an unpacked XfrmUserTmpl
      mark: an unpacked XfrmMark
      xfrm_if_id: the XFRM interface ID as an integer, or None
    """
    self._UpdatePolicyInfo(XFRM_MSG_NEWPOLICY, policy, tmpl, mark, xfrm_if_id)

  def UpdatePolicyInfo(self, policy, tmpl, mark, xfrm_if_id):
    """Update an existing policy in the Security Policy Database

    If the policy does not exist, then create it; otherwise, update the
    existing policy record.

    Args:
      policy: an unpacked XfrmUserpolicyInfo
      tmpl: an unpacked XfrmUserTmpl to update
      mark: an unpacked XfrmMark to match the existing policy or None
      xfrm_if_id: an XFRM interface ID or None
    """
    self._UpdatePolicyInfo(XFRM_MSG_UPDPOLICY, policy, tmpl, mark, xfrm_if_id)

  def DeletePolicyInfo(self, selector, direction, mark, xfrm_if_id=None):
    """Delete a policy from the Security Policy Database

    Args:
      selector: an XfrmSelector matching the policy to delete
      direction: policy direction
      mark: an unpacked XfrmMark to match the policy or None
    """
    nlattrs = []
    if mark is not None:
      nlattrs.append((XFRMA_MARK, mark))
    if xfrm_if_id is not None:
      nlattrs.append((XFRMA_IF_ID, struct.pack("=I", xfrm_if_id)))
    self.SendXfrmNlRequest(XFRM_MSG_DELPOLICY,
                           XfrmUserpolicyId(sel=selector, dir=direction),
                           nlattrs)

  # TODO: this function really needs to be in netlink.py
  def SendXfrmNlRequest(self, msg_type, req, nlattrs=None,
                        flags=netlink.NLM_F_ACK|netlink.NLM_F_REQUEST):
    """Sends a netlink request message

    Args:
      msg_type: an XFRM_MSG_* type
      req: an unpacked netlink request message body cstruct
      nlattrs: an unpacked list of two-tuples of (NLATTR_* type, body) where
          the body is an unpacked cstruct
      flags: a list of flags for the expected handling; if no flags are
          provided, an ACK response is assumed.
    """
    msg = req.Pack()
    if nlattrs is None:
      nlattrs = []
    for attr_type, attr_msg in nlattrs:
      # TODO: find a better way to deal with the fact that many XFRM messages
      # use nlattrs that aren't cstructs.
      #
      # This code allows callers to pass in either something that has a Pack()
      # method or a packed netlink attr, but not other types of attributes.
      # Alternatives include:
      #
      # 1. Require callers to marshal netlink attributes themselves and call
      #    _SendNlRequest directly. Delete this method.
      # 2. Rename this function to _SendXfrmNlRequestCstructOnly (or other name
      #    that makes it clear that this only takes cstructs). Switch callers
      #    that need non-cstruct elements to calling _SendNlRequest directly.
      # 3. Make this function somehow automatically detect what to do for
      #    all types of XFRM attributes today and in the future. This may be
      #    feasible because all XFRM attributes today occupy the same number
      #    space, but what about nested attributes? It is unlikley feasible via
      #    things like "if isinstance(attr_msg, str): ...", because that would
      #    not be able to determine the right size or byte order for non-struct
      #    types such as int.
      # 4. Define fictitious cstructs which have no correspondence to actual
      #    kernel structs such as the following to represent a raw integer.
      #    XfrmAttrOutputMark = cstruct.Struct("=I", mark)
      if hasattr(attr_msg, "Pack"):
        attr_msg = attr_msg.Pack()
      msg += self._NlAttr(attr_type, attr_msg)
    return self._SendNlRequest(msg_type, msg, flags)

  def AddSaInfo(self, src, dst, spi, mode, reqid, encryption, auth_trunc, aead,
                encap, mark, output_mark, is_update=False, xfrm_if_id=None):
    """Adds an IPsec security association.

    Args:
      src: A string, the source IP address. May be a wildcard in transport mode.
      dst: A string, the destination IP address. Forms part of the XFRM ID, and
        must match the destination address of the packets sent by this SA.
      spi: An integer, the SPI.
      mode: An IPsec mode such as XFRM_MODE_TRANSPORT.
      reqid: A request ID. Can be used in policies to match the SA.
      encryption: A tuple of an XfrmAlgo and raw key bytes, or None.
      auth_trunc: A tuple of an XfrmAlgoAuth and raw key bytes, or None.
      aead: A tuple of an XfrmAlgoAead and raw key bytes, or None.
      encap: An XfrmEncapTmpl structure, or None.
      mark: A mark match specifier, such as returned by ExactMatchMark(), or
        None for an SA that matches all possible marks.
      output_mark: An integer, the output mark. 0 means unset.
      is_update: If true, update an existing SA otherwise create a new SA. For
        compatibility reasons, this value defaults to False.
      xfrm_if_id: The XFRM interface ID, or None.
    """
    proto = IPPROTO_ESP
    xfrm_id = XfrmId((PaddedAddress(dst), spi, proto))
    family = AF_INET6 if ":" in dst else AF_INET

    nlattrs = ""
    if encryption is not None:
      enc, key = encryption
      nlattrs += self._NlAttr(XFRMA_ALG_CRYPT, enc.Pack() + key)

    if auth_trunc is not None:
      auth, key = auth_trunc
      nlattrs += self._NlAttr(XFRMA_ALG_AUTH_TRUNC, auth.Pack() + key)

    if aead is not None:
      aead_alg, key = aead
      nlattrs += self._NlAttr(XFRMA_ALG_AEAD, aead_alg.Pack() + key)

    # if a user provides either mark or mask, then we send the mark attribute
    if mark is not None:
      nlattrs += self._NlAttr(XFRMA_MARK, mark.Pack())
    if encap is not None:
      nlattrs += self._NlAttr(XFRMA_ENCAP, encap.Pack())
    if output_mark is not None:
      nlattrs += self._NlAttrU32(XFRMA_OUTPUT_MARK, output_mark)
    if xfrm_if_id is not None:
      nlattrs += self._NlAttrU32(XFRMA_IF_ID, xfrm_if_id)

    # The kernel ignores these on input, so make them empty.
    cur = XfrmLifetimeCur()
    stats = XfrmStats()
    seq = 0
    replay = _DEFAULT_REPLAY_WINDOW

    # The XFRM_STATE_AF_UNSPEC flag determines how AF_UNSPEC selectors behave.
    #
    # - If the flag is not set, an AF_UNSPEC selector has its family changed to
    #   the SA family, which in our case is the address family of dst.
    # - If the flag is set, an AF_UNSPEC selector is left as is. In transport
    #   mode this fails with EPROTONOSUPPORT, but in tunnel mode, it results in
    #   a dual-stack SA that can tunnel both IPv4 and IPv6 packets.
    #
    # This allows us to pass an empty selector to the kernel regardless of which
    # mode we're in: when creating transport mode SAs, the kernel will pick the
    # selector family based on the SA family, and when creating tunnel mode SAs,
    # we'll just create SAs that select both IPv4 and IPv6 traffic, and leave it
    # up to the policy selectors to determine what traffic we actually want to
    # transform.
    flags = XFRM_STATE_AF_UNSPEC if mode == XFRM_MODE_TUNNEL else 0
    selector = EmptySelector(AF_UNSPEC)

    sa = XfrmUsersaInfo((selector, xfrm_id, PaddedAddress(src), NO_LIFETIME_CFG,
                         cur, stats, seq, reqid, family, mode, replay, flags))
    msg = sa.Pack() + nlattrs
    flags = netlink.NLM_F_REQUEST | netlink.NLM_F_ACK
    nl_msg_type = XFRM_MSG_UPDSA if is_update else XFRM_MSG_NEWSA
    self._SendNlRequest(nl_msg_type, msg, flags)

  def DeleteSaInfo(self, dst, spi, proto, mark=None, xfrm_if_id=None):
    """Delete an SA from the SAD

    Args:
      dst: A string, the destination IP address. Forms part of the XFRM ID, and
        must match the destination address of the packets sent by this SA.
      spi: An integer, the SPI.
      proto: The protocol DB of the SA, such as IPPROTO_ESP.
      mark: A mark match specifier, such as returned by ExactMatchMark(), or
        None for an SA without a Mark attribute.
    """
    family = AF_INET6 if ":" in dst else AF_INET
    usersa_id = XfrmUsersaId((PaddedAddress(dst), spi, family, proto))
    nlattrs = []
    if mark is not None:
      nlattrs.append((XFRMA_MARK, mark))
    if xfrm_if_id is not None:
      nlattrs.append((XFRMA_IF_ID, struct.pack("=I", xfrm_if_id)))
    self.SendXfrmNlRequest(XFRM_MSG_DELSA, usersa_id, nlattrs)

  def AllocSpi(self, dst, proto, min_spi, max_spi):
    """Allocate (reserve) an SPI.

    This sends an XFRM_MSG_ALLOCSPI message and returns the resulting
    XfrmUsersaInfo struct.

    Args:
      dst: A string, the destination IP address. Forms part of the XFRM ID, and
        must match the destination address of the packets sent by this SA.
      proto: the protocol DB of the SA, such as IPPROTO_ESP.
      min_spi: The minimum value of the acceptable SPI range (inclusive).
      max_spi: The maximum value of the acceptable SPI range (inclusive).
    """
    spi = XfrmUserSpiInfo("\x00" * len(XfrmUserSpiInfo))
    spi.min = min_spi
    spi.max = max_spi
    spi.info.id.daddr = PaddedAddress(dst)
    spi.info.id.proto = proto
    spi.info.family = AF_INET6 if ":" in dst else AF_INET

    msg = spi.Pack()
    flags = netlink.NLM_F_REQUEST
    self._SendNlRequest(XFRM_MSG_ALLOCSPI, msg, flags)
    # Read the response message.
    data = self._Recv()
    nl_hdr, data = cstruct.Read(data, netlink.NLMsgHdr)
    if nl_hdr.type == XFRM_MSG_NEWSA:
      return XfrmUsersaInfo(data)
    if nl_hdr.type == netlink.NLMSG_ERROR:
      error = netlink.NLMsgErr(data).error
      raise IOError(error, os.strerror(-error))
    raise ValueError("Unexpected netlink message type: %d" % nl_hdr.type)

  def DumpSaInfo(self):
    return self._Dump(XFRM_MSG_GETSA, None, XfrmUsersaInfo, "")

  def DumpPolicyInfo(self):
    return self._Dump(XFRM_MSG_GETPOLICY, None, XfrmUserpolicyInfo, "")

  def FindSaInfo(self, spi):
    sainfo = [sa for sa, attrs in self.DumpSaInfo() if sa.id.spi == spi]
    return sainfo[0] if sainfo else None

  def FlushPolicyInfo(self):
    """Send a Netlink Request to Flush all records from the SPD"""
    flags = netlink.NLM_F_REQUEST | netlink.NLM_F_ACK
    self._SendNlRequest(XFRM_MSG_FLUSHPOLICY, "", flags)

  def FlushSaInfo(self):
    usersa_flush = XfrmUsersaFlush((IPSEC_PROTO_ANY,))
    flags = netlink.NLM_F_REQUEST | netlink.NLM_F_ACK
    self._SendNlRequest(XFRM_MSG_FLUSHSA, usersa_flush.Pack(), flags)

  def CreateTunnel(self, direction, selector, src, dst, spi, encryption,
                   auth_trunc, mark, output_mark, xfrm_if_id, match_method):
    """Create an XFRM Tunnel Consisting of a Policy and an SA.

    Create a unidirectional XFRM tunnel, which entails one Policy and one
    security association.

    Args:
      direction: XFRM_POLICY_IN or XFRM_POLICY_OUT
      selector: An XfrmSelector that specifies the packets to be transformed.
        This is only applied to the policy; the selector in the SA is always
        empty. If the passed-in selector is None, then the tunnel is made
        dual-stack. This requires two policies, one for IPv4 and one for IPv6.
      src: The source address of the tunneled packets
      dst: The destination address of the tunneled packets
      spi: The SPI for the IPsec SA that encapsulates the tunneled packet
      encryption: A tuple (XfrmAlgo, key), the encryption parameters.
      auth_trunc: A tuple (XfrmAlgoAuth, key), the authentication parameters.
      mark: An XfrmMark, the mark used for selecting packets to be tunneled, and
        for matching the security policy. None means unspecified.
      output_mark: The mark used to select the underlying network for packets
        outbound from xfrm. None means unspecified.
      xfrm_if_id: The ID of the XFRM interface to use or None.
      match_method: One of MATCH_METHOD_[MARK | ALL | IFID]. This determines how
        SAs and policies are matched.
    """
    outer_family = net_test.GetAddressFamily(net_test.GetAddressVersion(dst))

    # SA mark is currently unused due to UPDSA not updating marks.
    # Kept as documentation of ideal/desired behavior.
    if match_method == MATCH_METHOD_MARK:
      # sa_mark = mark
      tmpl_spi = 0
      if_id = None
    elif match_method == MATCH_METHOD_ALL:
      # sa_mark = mark
      tmpl_spi = spi
      if_id = xfrm_if_id
    elif match_method == MATCH_METHOD_IFID:
      # sa_mark = None
      tmpl_spi = 0
      if_id = xfrm_if_id
    else:
      raise ValueError("Unknown match_method supplied: %s" % match_method)

    # Device code does not use mark; during AllocSpi, the mark is unset, and
    # UPDSA does not update marks at this time. Actual use case will have no
    # mark set. Test this use case.
    self.AddSaInfo(src, dst, spi, XFRM_MODE_TUNNEL, 0, encryption, auth_trunc,
                   None, None, None, output_mark, xfrm_if_id=xfrm_if_id)

    if selector is None:
      selectors = [EmptySelector(AF_INET), EmptySelector(AF_INET6)]
    else:
      selectors = [selector]

    for selector in selectors:
      policy = UserPolicy(direction, selector)
      tmpl = UserTemplate(outer_family, tmpl_spi, 0, (src, dst))
      self.AddPolicyInfo(policy, tmpl, mark, xfrm_if_id=xfrm_if_id)

  def DeleteTunnel(self, direction, selector, dst, spi, mark, xfrm_if_id):
    if mark is not None:
      mark = ExactMatchMark(mark)

    self.DeleteSaInfo(dst, spi, IPPROTO_ESP, mark, xfrm_if_id)
    if selector is None:
      selectors = [EmptySelector(AF_INET), EmptySelector(AF_INET6)]
    else:
      selectors = [selector]
    for selector in selectors:
      self.DeletePolicyInfo(selector, direction, mark, xfrm_if_id)


if __name__ == "__main__":
  x = Xfrm()
  print x.DumpSaInfo()
  print x.DumpPolicyInfo()
