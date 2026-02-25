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

"""Classes for generic netlink."""

import collections
from socket import *  # pylint: disable=wildcard-import
import struct

import cstruct
import netlink

### Generic netlink constants. See include/uapi/linux/genetlink.h.
# The generic netlink control family.
GENL_ID_CTRL = 16

# Commands.
CTRL_CMD_GETFAMILY = 3

# Attributes.
CTRL_ATTR_FAMILY_ID = 1
CTRL_ATTR_FAMILY_NAME = 2
CTRL_ATTR_VERSION = 3
CTRL_ATTR_HDRSIZE = 4
CTRL_ATTR_MAXATTR = 5
CTRL_ATTR_OPS = 6
CTRL_ATTR_MCAST_GROUPS = 7

# Attributes netsted inside CTRL_ATTR_OPS.
CTRL_ATTR_OP_ID = 1
CTRL_ATTR_OP_FLAGS = 2


# Data structure formats.
# These aren't constants, they're classes. So, pylint: disable=invalid-name
Genlmsghdr = cstruct.Struct("genlmsghdr", "BBxx", "cmd version")


class GenericNetlink(netlink.NetlinkSocket):
  """Base class for all generic netlink classes."""

  NL_DEBUG = []

  def __init__(self):
    super(GenericNetlink, self).__init__(netlink.NETLINK_GENERIC)

  def _SendCommand(self, family, command, version, data, flags):
    genlmsghdr = Genlmsghdr((command, version))
    self._SendNlRequest(family, genlmsghdr.Pack() + data, flags)

  def _Dump(self, family, command, version):
    msg = Genlmsghdr((command, version))
    return super(GenericNetlink, self)._Dump(family, msg, Genlmsghdr, "")


class GenericNetlinkControl(GenericNetlink):
  """Generic netlink control class.

  This interface is used to manage other generic netlink families. We currently
  use it only to find the family ID for address families of interest."""

  def _DecodeOps(self, data):
    ops = []
    Op = collections.namedtuple("Op", ["id", "flags"])
    while data:
      # Skip the nest marker.
      datalen, index, data = data[:2], data[2:4], data[4:]

      nla, nla_data, data = self._ReadNlAttr(data)
      if nla.nla_type != CTRL_ATTR_OP_ID:
        raise ValueError("Expected CTRL_ATTR_OP_ID, got %d" % nla.nla_type)
      op_id = struct.unpack("=I", nla_data)[0]

      nla, nla_data, data = self._ReadNlAttr(data)
      if nla.nla_type != CTRL_ATTR_OP_FLAGS:
        raise ValueError("Expected CTRL_ATTR_OP_FLAGS, got %d" % nla.type)
      op_flags = struct.unpack("=I", nla_data)[0]

      ops.append(Op(op_id, op_flags))
    return ops

  def _Decode(self, command, msg, nla_type, nla_data):
    """Decodes generic netlink control attributes to human-readable format."""

    name = self._GetConstantName(__name__, nla_type, "CTRL_ATTR_")

    if name == "CTRL_ATTR_FAMILY_ID":
      data = struct.unpack("=H", nla_data)[0]
    elif name == "CTRL_ATTR_FAMILY_NAME":
      data = nla_data.strip("\x00")
    elif name in ["CTRL_ATTR_VERSION", "CTRL_ATTR_HDRSIZE", "CTRL_ATTR_MAXATTR"]:
      data = struct.unpack("=I", nla_data)[0]
    elif name == "CTRL_ATTR_OPS":
      data = self._DecodeOps(nla_data)
    else:
      data = nla_data

    return name, data

  def GetFamily(self, name):
    """Returns the family ID for the specified family name."""
    data = self._NlAttrStr(CTRL_ATTR_FAMILY_NAME, name)
    self._SendCommand(GENL_ID_CTRL, CTRL_CMD_GETFAMILY, 0, data, netlink.NLM_F_REQUEST)
    hdr, attrs = self._GetMsg(Genlmsghdr)
    return attrs["CTRL_ATTR_FAMILY_ID"]


if __name__ == "__main__":
  g = GenericNetlinkControl()
  print g.GetFamily("tcp_metrics")
