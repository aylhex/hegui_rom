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

"""Generic netlink interface to TCP metrics."""

from socket import *  # pylint: disable=wildcard-import
import struct

import cstruct
import genetlink
import net_test
import netlink


### TCP metrics constants. See include/uapi/linux/tcp_metrics.h.
# Family name and version
TCP_METRICS_GENL_NAME = "tcp_metrics"
TCP_METRICS_GENL_VERSION = 1

# Message types.
TCP_METRICS_CMD_GET = 1
TCP_METRICS_CMD_DEL = 2

# Attributes.
TCP_METRICS_ATTR_UNSPEC = 0
TCP_METRICS_ATTR_ADDR_IPV4 = 1
TCP_METRICS_ATTR_ADDR_IPV6 = 2
TCP_METRICS_ATTR_AGE = 3
TCP_METRICS_ATTR_TW_TSVAL = 4
TCP_METRICS_ATTR_TW_TS_STAMP = 5
TCP_METRICS_ATTR_VALS = 6
TCP_METRICS_ATTR_FOPEN_MSS = 7
TCP_METRICS_ATTR_FOPEN_SYN_DROPS = 8
TCP_METRICS_ATTR_FOPEN_SYN_DROP_TS = 9
TCP_METRICS_ATTR_FOPEN_COOKIE = 10
TCP_METRICS_ATTR_SADDR_IPV4 = 11
TCP_METRICS_ATTR_SADDR_IPV6 = 12
TCP_METRICS_ATTR_PAD = 13


class TcpMetrics(genetlink.GenericNetlink):

  NL_DEBUG = ["ALL"]

  def __init__(self):
    super(TcpMetrics, self).__init__()
    # Generic netlink family IDs are dynamically assigned. Find ours.
    ctrl = genetlink.GenericNetlinkControl()
    self.family = ctrl.GetFamily(TCP_METRICS_GENL_NAME)

  def _Decode(self, command, msg, nla_type, nla_data):
    """Decodes TCP metrics netlink attributes to human-readable format."""

    name = self._GetConstantName(__name__, nla_type, "TCP_METRICS_ATTR_")

    if name in ["TCP_METRICS_ATTR_ADDR_IPV4", "TCP_METRICS_ATTR_SADDR_IPV4"]:
      data = inet_ntop(AF_INET, nla_data)
    elif name in ["TCP_METRICS_ATTR_ADDR_IPV6", "TCP_METRICS_ATTR_SADDR_IPV6"]:
      data = inet_ntop(AF_INET6, nla_data)
    elif name in ["TCP_METRICS_ATTR_AGE"]:
      data = struct.unpack("=Q", nla_data)[0]
    elif name in ["TCP_METRICS_ATTR_TW_TSVAL", "TCP_METRICS_ATTR_TW_TS_STAMP"]:
      data = struct.unpack("=I", nla_data)[0]
    elif name == "TCP_METRICS_ATTR_FOPEN_MSS":
      data = struct.unpack("=H", nla_data)[0]
    elif name == "TCP_METRICS_ATTR_FOPEN_COOKIE":
      data = nla_data
    else:
      data = nla_data.encode("hex")

    return name, data

  def MaybeDebugCommand(self, command, unused_flags, data):
    if "ALL" not in self.NL_DEBUG and command not in self.NL_DEBUG:
      return
    parsed = self._ParseNLMsg(data, genetlink.Genlmsghdr)

  def _NlAttrSaddr(self, address):
    if ":" not in address:
      family = AF_INET
      nla_type = TCP_METRICS_ATTR_SADDR_IPV4
    else:
      family = AF_INET6
      nla_type = TCP_METRICS_ATTR_SADDR_IPV6
    return self._NlAttrIPAddress(nla_type, family, address)

  def _NlAttrTcpMetricsAddr(self, address, is_source):
    version = net_test.GetAddressVersion(address)
    family = net_test.GetAddressFamily(version)
    if version == 5:
      address = address.replace("::ffff:", "")
    nla_name = "TCP_METRICS_ATTR_%s_IPV%d" % (
        "SADDR" if is_source else "ADDR", version)
    nla_type = globals()[nla_name]
    return self._NlAttrIPAddress(nla_type, family, address)

  def _NlAttrAddr(self, address):
    return self._NlAttrTcpMetricsAddr(address, False)

  def _NlAttrSaddr(self, address):
    return self._NlAttrTcpMetricsAddr(address, True)

  def DumpMetrics(self):
    """Dumps all TCP metrics."""
    return self._Dump(self.family, TCP_METRICS_CMD_GET, 1)

  def GetMetrics(self, saddr, daddr):
    """Returns TCP metrics for the specified src/dst pair."""
    data = self._NlAttrSaddr(saddr) + self._NlAttrAddr(daddr)
    self._SendCommand(self.family, TCP_METRICS_CMD_GET, 1, data,
                      netlink.NLM_F_REQUEST)
    hdr, attrs = self._GetMsg(genetlink.Genlmsghdr)
    return attrs

  def DelMetrics(self, saddr, daddr):
    """Deletes TCP metrics for the specified src/dst pair."""
    data = self._NlAttrSaddr(saddr) + self._NlAttrAddr(daddr)
    self._SendCommand(self.family, TCP_METRICS_CMD_DEL, 1, data,
                      netlink.NLM_F_REQUEST)


if __name__ == "__main__":
  t = TcpMetrics()
  print t.DumpMetrics()
