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

"""Partial Python implementation of iproute functionality."""

# pylint: disable=g-bad-todo

from socket import AF_INET
from socket import AF_INET6

import errno
import os
import socket
import struct

import csocket
import cstruct
import netlink

### rtnetlink constants. See include/uapi/linux/rtnetlink.h.
# Message types.
RTM_NEWLINK = 16
RTM_DELLINK = 17
RTM_GETLINK = 18
RTM_NEWADDR = 20
RTM_DELADDR = 21
RTM_GETADDR = 22
RTM_NEWROUTE = 24
RTM_DELROUTE = 25
RTM_GETROUTE = 26
RTM_NEWNEIGH = 28
RTM_DELNEIGH = 29
RTM_GETNEIGH = 30
RTM_NEWRULE = 32
RTM_DELRULE = 33
RTM_GETRULE = 34

# Routing message type values (rtm_type).
RTN_UNSPEC = 0
RTN_UNICAST = 1
RTN_UNREACHABLE = 7
RTN_THROW = 9

# Routing protocol values (rtm_protocol).
RTPROT_UNSPEC = 0
RTPROT_BOOT = 3
RTPROT_STATIC = 4
RTPROT_RA = 9

# Route scope values (rtm_scope).
RT_SCOPE_UNIVERSE = 0
RT_SCOPE_LINK = 253

# Named routing tables.
RT_TABLE_UNSPEC = 0

# Routing attributes.
RTA_DST = 1
RTA_SRC = 2
RTA_IIF = 3
RTA_OIF = 4
RTA_GATEWAY = 5
RTA_PRIORITY = 6
RTA_PREFSRC = 7
RTA_METRICS = 8
RTA_CACHEINFO = 12
RTA_TABLE = 15
RTA_MARK = 16
RTA_PREF = 20
RTA_UID = 25

# Netlink groups.
RTMGRP_IPV6_IFADDR = 0x100

# Route metric attributes.
RTAX_MTU = 2
RTAX_HOPLIMIT = 10

# Data structure formats.
IfinfoMsg = cstruct.Struct(
    "IfinfoMsg", "=BBHiII", "family pad type index flags change")
RTMsg = cstruct.Struct(
    "RTMsg", "=BBBBBBBBI",
    "family dst_len src_len tos table protocol scope type flags")
RTACacheinfo = cstruct.Struct(
    "RTACacheinfo", "=IIiiI", "clntref lastuse expires error used")


### Interface address constants. See include/uapi/linux/if_addr.h.
# Interface address attributes.
IFA_ADDRESS = 1
IFA_LOCAL = 2
IFA_LABEL = 3
IFA_CACHEINFO = 6

# Address flags.
IFA_F_SECONDARY = 0x01
IFA_F_TEMPORARY = IFA_F_SECONDARY
IFA_F_NODAD = 0x02
IFA_F_OPTIMISTIC = 0x04
IFA_F_DADFAILED = 0x08
IFA_F_HOMEADDRESS = 0x10
IFA_F_DEPRECATED = 0x20
IFA_F_TENTATIVE = 0x40
IFA_F_PERMANENT = 0x80

# This cannot contain members that do not yet exist in older kernels, because
# GetIfaceStats will fail if the kernel returns fewer bytes than the size of
# RtnlLinkStats[64].
_LINK_STATS_MEMBERS = (
    "rx_packets tx_packets rx_bytes tx_bytes rx_errors tx_errors "
    "rx_dropped tx_dropped multicast collisions "
    "rx_length_errors rx_over_errors rx_crc_errors rx_frame_errors "
    "rx_fifo_errors rx_missed_errors tx_aborted_errors tx_carrier_errors "
    "tx_fifo_errors tx_heartbeat_errors tx_window_errors "
    "rx_compressed tx_compressed")

# Data structure formats.
IfAddrMsg = cstruct.Struct(
    "IfAddrMsg", "=BBBBI",
    "family prefixlen flags scope index")
IFACacheinfo = cstruct.Struct(
    "IFACacheinfo", "=IIII", "prefered valid cstamp tstamp")
NDACacheinfo = cstruct.Struct(
    "NDACacheinfo", "=IIII", "confirmed used updated refcnt")
RtnlLinkStats = cstruct.Struct(
    "RtnlLinkStats", "=IIIIIIIIIIIIIIIIIIIIIII", _LINK_STATS_MEMBERS)
RtnlLinkStats64 = cstruct.Struct(
    "RtnlLinkStats64", "=QQQQQQQQQQQQQQQQQQQQQQQ", _LINK_STATS_MEMBERS)

### Neighbour table entry constants. See include/uapi/linux/neighbour.h.
# Neighbour cache entry attributes.
NDA_DST = 1
NDA_LLADDR = 2
NDA_CACHEINFO = 3
NDA_PROBES = 4
NDA_IFINDEX = 8

# Neighbour cache entry states.
NUD_PERMANENT = 0x80

# Data structure formats.
NdMsg = cstruct.Struct(
    "NdMsg", "=BxxxiHBB",
    "family ifindex state flags type")


### FIB rule constants. See include/uapi/linux/fib_rules.h.
FRA_IIFNAME = 3
FRA_PRIORITY = 6
FRA_FWMARK = 10
FRA_SUPPRESS_PREFIXLEN = 14
FRA_TABLE = 15
FRA_FWMASK = 16
FRA_OIFNAME = 17
FRA_UID_RANGE = 20

# Data structure formats.
FibRuleUidRange = cstruct.Struct("FibRuleUidRange", "=II", "start end")

# Link constants. See include/uapi/linux/if_link.h.
IFLA_UNSPEC = 0
IFLA_ADDRESS = 1
IFLA_BROADCAST = 2
IFLA_IFNAME = 3
IFLA_MTU = 4
IFLA_LINK = 5
IFLA_QDISC = 6
IFLA_STATS = 7
IFLA_COST = 8
IFLA_PRIORITY = 9
IFLA_MASTER = 10
IFLA_WIRELESS = 11
IFLA_PROTINFO = 12
IFLA_TXQLEN = 13
IFLA_MAP = 14
IFLA_WEIGHT = 15
IFLA_OPERSTATE = 16
IFLA_LINKMODE = 17
IFLA_LINKINFO = 18
IFLA_NET_NS_PID = 19
IFLA_IFALIAS = 20
IFLA_STATS64 = 23
IFLA_AF_SPEC = 26
IFLA_GROUP = 27
IFLA_EXT_MASK = 29
IFLA_PROMISCUITY = 30
IFLA_NUM_TX_QUEUES = 31
IFLA_NUM_RX_QUEUES = 32
IFLA_CARRIER = 33
IFLA_CARRIER_CHANGES = 35
IFLA_PROTO_DOWN = 39
IFLA_GSO_MAX_SEGS = 40
IFLA_GSO_MAX_SIZE = 41
IFLA_PAD = 42
IFLA_XDP = 43
IFLA_EVENT = 44

# include/uapi/linux/if_link.h
IFLA_INFO_UNSPEC = 0
IFLA_INFO_KIND = 1
IFLA_INFO_DATA = 2
IFLA_INFO_XSTATS = 3

IFLA_XFRM_UNSPEC = 0
IFLA_XFRM_LINK = 1
IFLA_XFRM_IF_ID = 2

# include/uapi/linux/if_tunnel.h
IFLA_VTI_UNSPEC = 0
IFLA_VTI_LINK = 1
IFLA_VTI_IKEY = 2
IFLA_VTI_OKEY = 3
IFLA_VTI_LOCAL = 4
IFLA_VTI_REMOTE = 5


def CommandVerb(command):
  return ["NEW", "DEL", "GET", "SET"][command % 4]


def CommandSubject(command):
  return ["LINK", "ADDR", "ROUTE", "NEIGH", "RULE"][(command - 16) / 4]


def CommandName(command):
  try:
    return "RTM_%s%s" % (CommandVerb(command), CommandSubject(command))
  except IndexError:
    return "RTM_%d" % command


class IPRoute(netlink.NetlinkSocket):
  """Provides a tiny subset of iproute functionality."""

  def _NlAttrInterfaceName(self, nla_type, interface):
    return self._NlAttr(nla_type, interface + "\x00")

  def _GetConstantName(self, value, prefix):
    return super(IPRoute, self)._GetConstantName(__name__, value, prefix)

  def _Decode(self, command, msg, nla_type, nla_data, nested=0):
    """Decodes netlink attributes to Python types.

    Values for which the code knows the type (e.g., the fwmark ID in a
    RTM_NEWRULE command) are decoded to Python integers, strings, etc. Values
    of unknown type are returned as raw byte strings.

    Args:
      command: An integer.
        - If positive, the number of the rtnetlink command being carried out.
          This is used to interpret the attributes. For example, for an
          RTM_NEWROUTE command, attribute type 3 is the incoming interface and
          is an integer, but for a RTM_NEWRULE command, attribute type 3 is the
          incoming interface name and is a string.
        - If negative, one of the following (negative) values:
          - RTA_METRICS: Interpret as nested route metrics.
          - IFLA_LINKINFO: Nested interface information.
      family: The address family. Used to convert IP addresses into strings.
      nla_type: An integer, then netlink attribute type.
      nla_data: A byte string, the netlink attribute data.
      nested: An integer, how deep we're currently nested.

    Returns:
      A tuple (name, data):
       - name is a string (e.g., "FRA_PRIORITY") if we understood the attribute,
         or an integer if we didn't.
       - data can be an integer, a string, a nested dict of attributes as
         returned by _ParseAttributes (e.g., for RTA_METRICS), a cstruct.Struct
         (e.g., RTACacheinfo), etc. If we didn't understand the attribute, it
         will be the raw byte string.
    """
    if command == -RTA_METRICS:
      name = self._GetConstantName(nla_type, "RTAX_")
    elif command == -IFLA_LINKINFO:
      name = self._GetConstantName(nla_type, "IFLA_INFO_")
    elif command == -IFLA_INFO_DATA:
      name = self._GetConstantName(nla_type, "IFLA_VTI_")
    elif CommandSubject(command) == "ADDR":
      name = self._GetConstantName(nla_type, "IFA_")
    elif CommandSubject(command) == "LINK":
      name = self._GetConstantName(nla_type, "IFLA_")
    elif CommandSubject(command) == "RULE":
      name = self._GetConstantName(nla_type, "FRA_")
    elif CommandSubject(command) == "ROUTE":
      name = self._GetConstantName(nla_type, "RTA_")
    elif CommandSubject(command) == "NEIGH":
      name = self._GetConstantName(nla_type, "NDA_")
    else:
      # Don't know what this is. Leave it as an integer.
      name = nla_type

    if name in ["FRA_PRIORITY", "FRA_FWMARK", "FRA_TABLE", "FRA_FWMASK",
                "RTA_OIF", "RTA_PRIORITY", "RTA_TABLE", "RTA_MARK",
                "IFLA_MTU", "IFLA_TXQLEN", "IFLA_GROUP", "IFLA_EXT_MASK",
                "IFLA_PROMISCUITY", "IFLA_NUM_RX_QUEUES",
                "IFLA_NUM_TX_QUEUES", "NDA_PROBES", "RTAX_MTU",
                "RTAX_HOPLIMIT", "IFLA_CARRIER_CHANGES", "IFLA_GSO_MAX_SEGS",
                "IFLA_GSO_MAX_SIZE", "RTA_UID"]:
      data = struct.unpack("=I", nla_data)[0]
    elif name in ["IFLA_VTI_OKEY", "IFLA_VTI_IKEY"]:
      data = struct.unpack("!I", nla_data)[0]
    elif name == "FRA_SUPPRESS_PREFIXLEN":
      data = struct.unpack("=i", nla_data)[0]
    elif name in ["IFLA_LINKMODE", "IFLA_OPERSTATE", "IFLA_CARRIER"]:
      data = ord(nla_data)
    elif name in ["IFA_ADDRESS", "IFA_LOCAL", "RTA_DST", "RTA_SRC",
                  "RTA_GATEWAY", "RTA_PREFSRC", "NDA_DST"]:
      data = socket.inet_ntop(msg.family, nla_data)
    elif name in ["FRA_IIFNAME", "FRA_OIFNAME", "IFLA_IFNAME", "IFLA_QDISC",
                  "IFA_LABEL", "IFLA_INFO_KIND"]:
      data = nla_data.strip("\x00")
    elif name == "RTA_METRICS":
      data = self._ParseAttributes(-RTA_METRICS, None, nla_data, nested + 1)
    elif name == "IFLA_LINKINFO":
      data = self._ParseAttributes(-IFLA_LINKINFO, None, nla_data, nested + 1)
    elif name == "IFLA_INFO_DATA":
      data = self._ParseAttributes(-IFLA_INFO_DATA, None, nla_data)
    elif name == "RTA_CACHEINFO":
      data = RTACacheinfo(nla_data)
    elif name == "IFA_CACHEINFO":
      data = IFACacheinfo(nla_data)
    elif name == "NDA_CACHEINFO":
      data = NDACacheinfo(nla_data)
    elif name in ["NDA_LLADDR", "IFLA_ADDRESS", "IFLA_BROADCAST"]:
      data = ":".join(x.encode("hex") for x in nla_data)
    elif name == "FRA_UID_RANGE":
      data = FibRuleUidRange(nla_data)
    elif name == "IFLA_STATS":
      data = RtnlLinkStats(nla_data)
    elif name == "IFLA_STATS64":
      data = RtnlLinkStats64(nla_data)
    else:
      data = nla_data

    return name, data

  def __init__(self):
    super(IPRoute, self).__init__(netlink.NETLINK_ROUTE)

  def _AddressFamily(self, version):
    return {4: AF_INET, 6: AF_INET6}[version]

  def _SendNlRequest(self, command, data, flags=0):
    """Sends a netlink request and expects an ack."""

    flags |= netlink.NLM_F_REQUEST
    if CommandVerb(command) != "GET":
      flags |= netlink.NLM_F_ACK
    if CommandVerb(command) == "NEW":
      if flags & (netlink.NLM_F_REPLACE | netlink.NLM_F_CREATE) == 0:
        flags |= netlink.NLM_F_CREATE | netlink.NLM_F_EXCL

    super(IPRoute, self)._SendNlRequest(command, data, flags)

  def _Rule(self, version, is_add, rule_type, table, match_nlattr, priority):
    """Python equivalent of "ip rule <add|del> <match_cond> lookup <table>".

    Args:
      version: An integer, 4 or 6.
      is_add: True to add a rule, False to delete it.
      rule_type: Type of rule, e.g., RTN_UNICAST or RTN_UNREACHABLE.
      table: If nonzero, rule looks up this table.
      match_nlattr: A blob of struct nlattrs that express the match condition.
        If None, match everything.
      priority: An integer, the priority.

    Raises:
      IOError: If the netlink request returns an error.
      ValueError: If the kernel's response could not be parsed.
    """
    # Create a struct rtmsg specifying the table and the given match attributes.
    family = self._AddressFamily(version)
    rtmsg = RTMsg((family, 0, 0, 0, RT_TABLE_UNSPEC,
                   RTPROT_STATIC, RT_SCOPE_UNIVERSE, rule_type, 0)).Pack()
    rtmsg += self._NlAttrU32(FRA_PRIORITY, priority)
    if match_nlattr:
      rtmsg += match_nlattr
    if table:
      rtmsg += self._NlAttrU32(FRA_TABLE, table)

    # Create a netlink request containing the rtmsg.
    command = RTM_NEWRULE if is_add else RTM_DELRULE
    self._SendNlRequest(command, rtmsg)

  def DeleteRulesAtPriority(self, version, priority):
    family = self._AddressFamily(version)
    rtmsg = RTMsg((family, 0, 0, 0, RT_TABLE_UNSPEC,
                   RTPROT_STATIC, RT_SCOPE_UNIVERSE, RTN_UNICAST, 0)).Pack()
    rtmsg += self._NlAttrU32(FRA_PRIORITY, priority)
    while True:
      try:
        self._SendNlRequest(RTM_DELRULE, rtmsg)
      except IOError, e:
        if e.errno == errno.ENOENT:
          break
        else:
          raise

  def FwmarkRule(self, version, is_add, fwmark, fwmask, table, priority):
    nlattr = self._NlAttrU32(FRA_FWMARK, fwmark)
    nlattr += self._NlAttrU32(FRA_FWMASK, fwmask)
    return self._Rule(version, is_add, RTN_UNICAST, table, nlattr, priority)

  def IifRule(self, version, is_add, iif, table, priority):
    nlattr = self._NlAttrInterfaceName(FRA_IIFNAME, iif)
    return self._Rule(version, is_add, RTN_UNICAST, table, nlattr, priority)

  def OifRule(self, version, is_add, oif, table, priority):
    nlattr = self._NlAttrInterfaceName(FRA_OIFNAME, oif)
    return self._Rule(version, is_add, RTN_UNICAST, table, nlattr, priority)

  def UidRangeRule(self, version, is_add, start, end, table, priority):
    nlattr = self._NlAttrInterfaceName(FRA_IIFNAME, "lo")
    nlattr += self._NlAttr(FRA_UID_RANGE,
                           FibRuleUidRange((start, end)).Pack())
    return self._Rule(version, is_add, RTN_UNICAST, table, nlattr, priority)

  def UnreachableRule(self, version, is_add, priority):
    return self._Rule(version, is_add, RTN_UNREACHABLE, None, None, priority)

  def DefaultRule(self, version, is_add, table, priority):
    return self.FwmarkRule(version, is_add, 0, 0, table, priority)

  def CommandToString(self, command, data):
    try:
      name = CommandName(command)
      subject = CommandSubject(command)
      struct_type = {
          "ADDR": IfAddrMsg,
          "LINK": IfinfoMsg,
          "NEIGH": NdMsg,
          "ROUTE": RTMsg,
          "RULE": RTMsg,
      }[subject]
      parsed = self._ParseNLMsg(data, struct_type)
      return "%s %s" % (name, str(parsed))
    except IndexError:
      raise ValueError("Don't know how to print command type %s" % name)

  def MaybeDebugCommand(self, command, unused_flags, data):
    subject = CommandSubject(command)
    if "ALL" not in self.NL_DEBUG and subject not in self.NL_DEBUG:
      return
    print self.CommandToString(command, data)

  def MaybeDebugMessage(self, message):
    hdr = netlink.NLMsgHdr(message)
    self.MaybeDebugCommand(hdr.type, message)

  def PrintMessage(self, message):
    hdr = netlink.NLMsgHdr(message)
    print self.CommandToString(hdr.type, message)

  def DumpRules(self, version):
    """Returns the IP rules for the specified IP version."""
    # Create a struct rtmsg specifying the table and the given match attributes.
    family = self._AddressFamily(version)
    rtmsg = RTMsg((family, 0, 0, 0, 0, 0, 0, 0, 0))
    return self._Dump(RTM_GETRULE, rtmsg, RTMsg, "")

  def DumpLinks(self):
    ifinfomsg = IfinfoMsg((0, 0, 0, 0, 0, 0))
    return self._Dump(RTM_GETLINK, ifinfomsg, IfinfoMsg, "")

  def DumpAddresses(self, version):
    family = self._AddressFamily(version)
    ifaddrmsg = IfAddrMsg((family, 0, 0, 0, 0))
    return self._Dump(RTM_GETADDR, ifaddrmsg, IfAddrMsg, "")

  def _Address(self, version, command, addr, prefixlen, flags, scope, ifindex):
    """Adds or deletes an IP address."""
    family = self._AddressFamily(version)
    ifaddrmsg = IfAddrMsg((family, prefixlen, flags, scope, ifindex)).Pack()
    ifaddrmsg += self._NlAttrIPAddress(IFA_ADDRESS, family, addr)
    if version == 4:
      ifaddrmsg += self._NlAttrIPAddress(IFA_LOCAL, family, addr)
    self._SendNlRequest(command, ifaddrmsg)

  def _WaitForAddress(self, sock, address, ifindex):
    # IPv6 addresses aren't immediately usable when the netlink ACK comes back.
    # Even if DAD is disabled via IFA_F_NODAD or on the interface, when the ACK
    # arrives the input route has not yet been added to the local table. The
    # route is added in addrconf_dad_begin with a delayed timer of 0, but if
    # the system is under load, we could win the race against that timer and
    # cause the tests to be flaky. So, wait for RTM_NEWADDR to arrive
    csocket.SetSocketTimeout(sock, 100)
    while True:
      try:
        data = sock.recv(4096)
      except EnvironmentError as e:
        raise AssertionError("Address %s did not appear on ifindex %d: %s" %
                             (address, ifindex, e.strerror))
      msg, attrs = self._ParseNLMsg(data, IfAddrMsg)[0]
      if msg.index == ifindex and attrs["IFA_ADDRESS"] == address:
        return

  def AddAddress(self, address, prefixlen, ifindex):
    """Adds a statically-configured IP address to an interface.

    The address is created with flags IFA_F_PERMANENT, and, if IPv6,
    IFA_F_NODAD. The requested scope is RT_SCOPE_UNIVERSE, but at least for
    IPv6, is instead determined by the kernel.

    In order to avoid races (see comments in _WaitForAddress above), when
    configuring IPv6 addresses, the method blocks until it receives an
    RTM_NEWADDR from the kernel confirming that the address has been added.
    If the address does not appear within 100ms, AssertionError is thrown.

    Args:
      address: A string, the IP address to configure.
      prefixlen: The prefix length passed to the kernel. If not /32 for IPv4 or
        /128 for IPv6, the kernel creates an implicit directly-connected route.
      ifindex: The interface index to add the address to.

    Raises:
      AssertionError: An IPv6 address was requested, and it did not appear
        within the timeout.
    """
    version = csocket.AddressVersion(address)

    flags = IFA_F_PERMANENT
    if version == 6:
      flags |= IFA_F_NODAD
      sock = self._OpenNetlinkSocket(netlink.NETLINK_ROUTE,
                                     groups=RTMGRP_IPV6_IFADDR)

    self._Address(version, RTM_NEWADDR, address, prefixlen, flags,
                  RT_SCOPE_UNIVERSE, ifindex)

    if version == 6:
      self._WaitForAddress(sock, address, ifindex)

  def DelAddress(self, address, prefixlen, ifindex):
    self._Address(csocket.AddressVersion(address),
                  RTM_DELADDR, address, prefixlen, 0, 0, ifindex)

  def GetAddress(self, address, ifindex=0):
    """Returns an ifaddrmsg for the requested address."""
    if ":" not in address:
      # The address is likely an IPv4 address.  RTM_GETADDR without the
      # NLM_F_DUMP flag is not supported by the kernel.  We do not currently
      # implement parsing dump results.
      raise NotImplementedError("IPv4 RTM_GETADDR not implemented.")
    self._Address(6, RTM_GETADDR, address, 0, 0, RT_SCOPE_UNIVERSE, ifindex)
    return self._GetMsg(IfAddrMsg)

  def _Route(self, version, proto, command, table, dest, prefixlen, nexthop,
             dev, mark, uid, route_type=RTN_UNICAST, priority=None, iif=None):
    """Adds, deletes, or queries a route."""
    family = self._AddressFamily(version)
    scope = RT_SCOPE_UNIVERSE if nexthop else RT_SCOPE_LINK
    rtmsg = RTMsg((family, prefixlen, 0, 0, RT_TABLE_UNSPEC,
                   proto, scope, route_type, 0)).Pack()
    if command == RTM_NEWROUTE and not table:
      # Don't allow setting routes in table 0, since its behaviour is confusing
      # and differs between IPv4 and IPv6.
      raise ValueError("Cowardly refusing to add a route to table 0")
    if table:
      rtmsg += self._NlAttrU32(FRA_TABLE, table)
    if dest != "default":  # The default is the default route.
      rtmsg += self._NlAttrIPAddress(RTA_DST, family, dest)
    if nexthop:
      rtmsg += self._NlAttrIPAddress(RTA_GATEWAY, family, nexthop)
    if dev:
      rtmsg += self._NlAttrU32(RTA_OIF, dev)
    if mark is not None:
      rtmsg += self._NlAttrU32(RTA_MARK, mark)
    if uid is not None:
      rtmsg += self._NlAttrU32(RTA_UID, uid)
    if priority is not None:
      rtmsg += self._NlAttrU32(RTA_PRIORITY, priority)
    if iif is not None:
      rtmsg += self._NlAttrU32(RTA_IIF, iif)
    self._SendNlRequest(command, rtmsg)

  def AddRoute(self, version, table, dest, prefixlen, nexthop, dev):
    self._Route(version, RTPROT_STATIC, RTM_NEWROUTE, table, dest, prefixlen,
                nexthop, dev, None, None)

  def DelRoute(self, version, table, dest, prefixlen, nexthop, dev):
    self._Route(version, RTPROT_STATIC, RTM_DELROUTE, table, dest, prefixlen,
                nexthop, dev, None, None)

  def GetRoutes(self, dest, oif, mark, uid, iif=None):
    version = csocket.AddressVersion(dest)
    prefixlen = {4: 32, 6: 128}[version]
    self._Route(version, RTPROT_STATIC, RTM_GETROUTE, 0, dest, prefixlen, None,
                oif, mark, uid, iif=iif)
    data = self._Recv()
    # The response will either be an error or a list of routes.
    if netlink.NLMsgHdr(data).type == netlink.NLMSG_ERROR:
      self._ParseAck(data)
    routes = self._GetMsgList(RTMsg, data, False)
    return routes

  def DumpRoutes(self, version, ifindex):
    rtmsg = RTMsg(family=self._AddressFamily(version))
    return [(m, r) for (m, r) in self._Dump(RTM_GETROUTE, rtmsg, RTMsg, "")
            if r['RTA_TABLE'] == ifindex]

  def _Neighbour(self, version, is_add, addr, lladdr, dev, state, flags=0):
    """Adds or deletes a neighbour cache entry."""
    family = self._AddressFamily(version)

    # Convert the link-layer address to a raw byte string.
    if is_add and lladdr:
      lladdr = lladdr.split(":")
      if len(lladdr) != 6:
        raise ValueError("Invalid lladdr %s" % ":".join(lladdr))
      lladdr = "".join(chr(int(hexbyte, 16)) for hexbyte in lladdr)

    ndmsg = NdMsg((family, dev, state, 0, RTN_UNICAST)).Pack()
    ndmsg += self._NlAttrIPAddress(NDA_DST, family, addr)
    if is_add and lladdr:
      ndmsg += self._NlAttr(NDA_LLADDR, lladdr)
    command = RTM_NEWNEIGH if is_add else RTM_DELNEIGH
    self._SendNlRequest(command, ndmsg, flags)

  def AddNeighbour(self, version, addr, lladdr, dev):
    self._Neighbour(version, True, addr, lladdr, dev, NUD_PERMANENT)

  def DelNeighbour(self, version, addr, lladdr, dev):
    self._Neighbour(version, False, addr, lladdr, dev, 0)

  def UpdateNeighbour(self, version, addr, lladdr, dev, state):
    self._Neighbour(version, True, addr, lladdr, dev, state,
                    flags=netlink.NLM_F_REPLACE)

  def DumpNeighbours(self, version, ifindex):
    ndmsg = NdMsg((self._AddressFamily(version), 0, 0, 0, 0))
    attrs = self._NlAttrU32(NDA_IFINDEX, ifindex) if ifindex else ""
    return self._Dump(RTM_GETNEIGH, ndmsg, NdMsg, attrs)

  def ParseNeighbourMessage(self, msg):
    msg, _ = self._ParseNLMsg(msg, NdMsg)
    return msg

  def DeleteLink(self, dev_name):
    ifinfo = IfinfoMsg().Pack()
    ifinfo += self._NlAttrStr(IFLA_IFNAME, dev_name)
    return self._SendNlRequest(RTM_DELLINK, ifinfo)

  def GetIfinfo(self, dev_name):
    """Fetches information about the specified interface.

    Args:
      dev_name: A string, the name of the interface.

    Returns:
      A tuple containing an IfinfoMsg struct and raw, undecoded attributes.
    """
    ifinfo = IfinfoMsg().Pack()
    ifinfo += self._NlAttrStr(IFLA_IFNAME, dev_name)
    self._SendNlRequest(RTM_GETLINK, ifinfo)
    hdr, data = cstruct.Read(self._Recv(), netlink.NLMsgHdr)
    if hdr.type == RTM_NEWLINK:
      return cstruct.Read(data, IfinfoMsg)
    elif hdr.type == netlink.NLMSG_ERROR:
      error = netlink.NLMsgErr(data).error
      raise IOError(error, os.strerror(-error))
    else:
      raise ValueError("Unknown Netlink Message Type %d" % hdr.type)

  def GetIfIndex(self, dev_name):
    """Returns the interface index for the specified interface."""
    ifinfo, _ = self.GetIfinfo(dev_name)
    return ifinfo.index

  def GetIfaceStats(self, dev_name):
    """Returns an RtnlLinkStats64 stats object for the specified interface."""
    _, attrs = self.GetIfinfo(dev_name)
    attrs = self._ParseAttributes(RTM_NEWLINK, IfinfoMsg, attrs)
    return attrs["IFLA_STATS64"]

  def GetIfinfoData(self, dev_name):
    """Returns an IFLA_INFO_DATA dict object for the specified interface."""
    _, attrs = self.GetIfinfo(dev_name)
    attrs = self._ParseAttributes(RTM_NEWLINK, IfinfoMsg, attrs)
    return attrs["IFLA_LINKINFO"]["IFLA_INFO_DATA"]

  def GetRxTxPackets(self, dev_name):
    stats = self.GetIfaceStats(dev_name)
    return stats.rx_packets, stats.tx_packets

  def CreateVirtualTunnelInterface(self, dev_name, local_addr, remote_addr,
                                   i_key=None, o_key=None, is_update=False):
    """
    Create a Virtual Tunnel Interface that provides a proxy interface
    for IPsec tunnels.

    The VTI Newlink structure is a series of nested netlink
    attributes following a mostly-ignored 'struct ifinfomsg':

    NLMSGHDR (type=RTM_NEWLINK)
    |
    |-{IfinfoMsg}
    |
    |-IFLA_IFNAME = <user-provided ifname>
    |
    |-IFLA_LINKINFO
      |
      |-IFLA_INFO_KIND = "vti"
      |
      |-IFLA_INFO_DATA
        |
        |-IFLA_VTI_LOCAL = <local addr>
        |-IFLA_VTI_REMOTE = <remote addr>
        |-IFLA_VTI_LINK = ????
        |-IFLA_VTI_OKEY = [outbound mark]
        |-IFLA_VTI_IKEY = [inbound mark]
    """
    family = AF_INET6 if ":" in remote_addr else AF_INET

    ifinfo = IfinfoMsg().Pack()
    ifinfo += self._NlAttrStr(IFLA_IFNAME, dev_name)

    linkinfo = self._NlAttrStr(IFLA_INFO_KIND,
        {AF_INET6: "vti6", AF_INET: "vti"}[family])

    ifdata = self._NlAttrIPAddress(IFLA_VTI_LOCAL, family, local_addr)
    ifdata += self._NlAttrIPAddress(IFLA_VTI_REMOTE, family,
                                    remote_addr)
    if i_key is not None:
      ifdata += self._NlAttrU32(IFLA_VTI_IKEY, socket.htonl(i_key))
    if o_key is not None:
      ifdata += self._NlAttrU32(IFLA_VTI_OKEY, socket.htonl(o_key))
    linkinfo += self._NlAttr(IFLA_INFO_DATA, ifdata)

    ifinfo += self._NlAttr(IFLA_LINKINFO, linkinfo)

    # Always pass CREATE to prevent _SendNlRequest() from incorrectly
    # guessing the flags.
    flags = netlink.NLM_F_CREATE
    if not is_update:
      flags |= netlink.NLM_F_EXCL
    return self._SendNlRequest(RTM_NEWLINK, ifinfo, flags)

  def CreateXfrmInterface(self, dev_name, xfrm_if_id, underlying_ifindex):
    """Creates an XFRM interface with the specified parameters."""
    # The netlink attribute structure is essentially identical to the one
    # for VTI above (q.v).
    ifdata = self._NlAttrU32(IFLA_XFRM_LINK, underlying_ifindex)
    ifdata += self._NlAttrU32(IFLA_XFRM_IF_ID, xfrm_if_id)

    linkinfo = self._NlAttrStr(IFLA_INFO_KIND, "xfrm")
    linkinfo += self._NlAttr(IFLA_INFO_DATA, ifdata)

    msg = IfinfoMsg().Pack()
    msg += self._NlAttrStr(IFLA_IFNAME, dev_name)
    msg += self._NlAttr(IFLA_LINKINFO, linkinfo)

    return self._SendNlRequest(RTM_NEWLINK, msg)


if __name__ == "__main__":
  iproute = IPRoute()
  iproute.DEBUG = True
  iproute.DumpRules(6)
  iproute.DumpLinks()
  print iproute.GetRoutes("2001:4860:4860::8888", 0, 0, None)
