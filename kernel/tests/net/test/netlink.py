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

import os
import socket
import struct
import sys

import cstruct
import util

### Base netlink constants. See include/uapi/linux/netlink.h.
NETLINK_ROUTE = 0
NETLINK_SOCK_DIAG = 4
NETLINK_XFRM = 6
NETLINK_GENERIC = 16

# Request constants.
NLM_F_REQUEST = 1
NLM_F_ACK = 4
NLM_F_REPLACE = 0x100
NLM_F_EXCL = 0x200
NLM_F_CREATE = 0x400
NLM_F_DUMP = 0x300

# Message types.
NLMSG_ERROR = 2
NLMSG_DONE = 3

# Data structure formats.
# These aren't constants, they're classes. So, pylint: disable=invalid-name
NLMsgHdr = cstruct.Struct("NLMsgHdr", "=LHHLL", "length type flags seq pid")
NLMsgErr = cstruct.Struct("NLMsgErr", "=i", "error")
NLAttr = cstruct.Struct("NLAttr", "=HH", "nla_len nla_type")

# Alignment / padding.
NLA_ALIGNTO = 4

# List of attributes that can appear more than once in a given netlink message.
# These can appear more than once but don't seem to contain any data.
DUP_ATTRS_OK = ["INET_DIAG_NONE", "IFLA_PAD"]

class NetlinkSocket(object):
  """A basic netlink socket object."""

  BUFSIZE = 65536
  DEBUG = False
  # List of netlink messages to print, e.g., [], ["NEIGH", "ROUTE"], or ["ALL"]
  NL_DEBUG = []

  def _Debug(self, s):
    if self.DEBUG:
      print s

  def _NlAttr(self, nla_type, data):
    datalen = len(data)
    # Pad the data if it's not a multiple of NLA_ALIGNTO bytes long.
    padding = "\x00" * util.GetPadLength(NLA_ALIGNTO, datalen)
    nla_len = datalen + len(NLAttr)
    return NLAttr((nla_len, nla_type)).Pack() + data + padding

  def _NlAttrIPAddress(self, nla_type, family, address):
    return self._NlAttr(nla_type, socket.inet_pton(family, address))

  def _NlAttrStr(self, nla_type, value):
    value = value + "\x00"
    return self._NlAttr(nla_type, value.encode("UTF-8"))

  def _NlAttrU32(self, nla_type, value):
    return self._NlAttr(nla_type, struct.pack("=I", value))

  def _GetConstantName(self, module, value, prefix):
    thismodule = sys.modules[module]
    for name in dir(thismodule):
      if name.startswith("INET_DIAG_BC"):
        continue
      if (name.startswith(prefix) and
          not name.startswith(prefix + "F_") and
          name.isupper() and getattr(thismodule, name) == value):
          return name
    return value

  def _Decode(self, command, msg, nla_type, nla_data):
    """No-op, nonspecific version of decode."""
    return nla_type, nla_data

  def _ReadNlAttr(self, data):
    # Read the nlattr header.
    nla, data = cstruct.Read(data, NLAttr)

    # Read the data.
    datalen = nla.nla_len - len(nla)
    padded_len = util.GetPadLength(NLA_ALIGNTO, datalen) + datalen
    nla_data, data = data[:datalen], data[padded_len:]

    return nla, nla_data, data

  def _ParseAttributes(self, command, msg, data, nested=0):
    """Parses and decodes netlink attributes.

    Takes a block of NLAttr data structures, decodes them using Decode, and
    returns the result in a dict keyed by attribute number.

    Args:
      command: An integer, the rtnetlink command being carried out.
      msg: A Struct, the type of the data after the netlink header.
      data: A byte string containing a sequence of NLAttr data structures.
      nested: An integer, how deep we're currently nested.

    Returns:
      A dictionary mapping attribute types (integers) to decoded values.

    Raises:
      ValueError: There was a duplicate attribute type.
    """
    attributes = {}
    while data:
      nla, nla_data, data = self._ReadNlAttr(data)

      # If it's an attribute we know about, try to decode it.
      nla_name, nla_data = self._Decode(command, msg, nla.nla_type, nla_data)

      if nla_name in attributes and nla_name not in DUP_ATTRS_OK:
        raise ValueError("Duplicate attribute %s" % nla_name)

      attributes[nla_name] = nla_data
      if not nested:
        self._Debug("      %s" % (str((nla_name, nla_data))))

    return attributes

  def _OpenNetlinkSocket(self, family, groups=None):
    sock = socket.socket(socket.AF_NETLINK, socket.SOCK_RAW, family)
    if groups:
      sock.bind((0,  groups))
    sock.connect((0, 0))  # The kernel.
    return sock

  def __init__(self, family):
    # Global sequence number.
    self.seq = 0
    self.sock = self._OpenNetlinkSocket(family)
    self.pid = self.sock.getsockname()[1]

  def MaybeDebugCommand(self, command, flags, data):
    # Default no-op implementation to be overridden by subclasses.
    pass

  def _Send(self, msg):
    # self._Debug(msg.encode("hex"))
    self.seq += 1
    self.sock.send(msg)

  def _Recv(self):
    data = self.sock.recv(self.BUFSIZE)
    # self._Debug(data.encode("hex"))
    return data

  def _ExpectDone(self):
    response = self._Recv()
    hdr = NLMsgHdr(response)
    if hdr.type != NLMSG_DONE:
      raise ValueError("Expected DONE, got type %d" % hdr.type)

  def _ParseAck(self, response):
    # Find the error code.
    hdr, data = cstruct.Read(response, NLMsgHdr)
    if hdr.type == NLMSG_ERROR:
      error = NLMsgErr(data).error
      if error:
        raise IOError(-error, os.strerror(-error))
    else:
      raise ValueError("Expected ACK, got type %d" % hdr.type)

  def _ExpectAck(self):
    response = self._Recv()
    self._ParseAck(response)

  def _SendNlRequest(self, command, data, flags):
    """Sends a netlink request and expects an ack."""
    length = len(NLMsgHdr) + len(data)
    nlmsg = NLMsgHdr((length, command, flags, self.seq, self.pid)).Pack()

    self.MaybeDebugCommand(command, flags, nlmsg + data)

    # Send the message.
    self._Send(nlmsg + data)

    if flags & NLM_F_ACK:
      self._ExpectAck()

  def _ParseNLMsg(self, data, msgtype):
    """Parses a Netlink message into a header and a dictionary of attributes."""
    nlmsghdr, data = cstruct.Read(data, NLMsgHdr)
    self._Debug("  %s" % nlmsghdr)

    if nlmsghdr.type == NLMSG_ERROR or nlmsghdr.type == NLMSG_DONE:
      print "done"
      return (None, None), data

    nlmsg, data = cstruct.Read(data, msgtype)
    self._Debug("    %s" % nlmsg)

    # Parse the attributes in the nlmsg.
    attrlen = nlmsghdr.length - len(nlmsghdr) - len(nlmsg)
    attributes = self._ParseAttributes(nlmsghdr.type, nlmsg, data[:attrlen])
    data = data[attrlen:]
    return (nlmsg, attributes), data

  def _GetMsg(self, msgtype):
    data = self._Recv()
    if NLMsgHdr(data).type == NLMSG_ERROR:
      self._ParseAck(data)
    return self._ParseNLMsg(data, msgtype)[0]

  def _GetMsgList(self, msgtype, data, expect_done):
    out = []
    while data:
      msg, data = self._ParseNLMsg(data, msgtype)
      if msg is None:
        break
      out.append(msg)
    if expect_done:
      self._ExpectDone()
    return out

  def _Dump(self, command, msg, msgtype, attrs):
    """Sends a dump request and returns a list of decoded messages.

    Args:
      command: An integer, the command to run (e.g., RTM_NEWADDR).
      msg: A struct, the request (e.g., a RTMsg). May be None.
      msgtype: A cstruct.Struct, the data type to parse the dump results as.
      attrs: A string, the raw bytes of any request attributes to include.

    Returns:
      A list of (msg, attrs) tuples where msg is of type msgtype and attrs is
      a dict of attributes.
    """
    # Create a netlink dump request containing the msg.
    flags = NLM_F_DUMP | NLM_F_REQUEST
    msg = "" if msg is None else msg.Pack()
    length = len(NLMsgHdr) + len(msg) + len(attrs)
    nlmsghdr = NLMsgHdr((length, command, flags, self.seq, self.pid))

    # Send the request.
    request = nlmsghdr.Pack() + msg + attrs
    self.MaybeDebugCommand(command, flags, request)
    self._Send(request)

    # Keep reading netlink messages until we get a NLMSG_DONE.
    out = []
    while True:
      data = self._Recv()
      response_type = NLMsgHdr(data).type
      if response_type == NLMSG_DONE:
        break
      elif response_type == NLMSG_ERROR:
        # Likely means that the kernel didn't like our dump request.
        # Parse the error and throw an exception.
        self._ParseAck(data)
      out.extend(self._GetMsgList(msgtype, data, False))

    return out
