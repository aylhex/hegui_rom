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

"""Python wrapper for C socket calls and data structures."""

import ctypes
import ctypes.util
import os
import re
import socket
import struct

import cstruct
import util


# Data structures.
# These aren't constants, they're classes. So, pylint: disable=invalid-name
CMsgHdr = cstruct.Struct("cmsghdr", "@Lii", "len level type")
Iovec = cstruct.Struct("iovec", "@PL", "base len")
MsgHdr = cstruct.Struct("msghdr", "@LLPLPLi",
                        "name namelen iov iovlen control msg_controllen flags")
SockaddrIn = cstruct.Struct("sockaddr_in", "=HH4sxxxxxxxx", "family port addr")
SockaddrIn6 = cstruct.Struct("sockaddr_in6", "=HHI16sI",
                             "family port flowinfo addr scope_id")
SockaddrStorage = cstruct.Struct("sockaddr_storage", "=H126s", "family data")
SockExtendedErr = cstruct.Struct("sock_extended_err", "@IBBBxII",
                                 "errno origin type code info data")
InPktinfo = cstruct.Struct("in_pktinfo", "@i4s4s", "ifindex spec_dst addr")
In6Pktinfo = cstruct.Struct("in6_pktinfo", "@16si", "addr ifindex")

# Constants.
# IPv4 socket options and cmsg types.
IP_TTL = 2
IP_MTU_DISCOVER = 10
IP_PKTINFO = 8
IP_RECVERR = 11
IP_RECVTTL = 12
IP_MTU = 14

# IPv6 socket options and cmsg types.
IPV6_MTU_DISCOVER = 23
IPV6_RECVERR = 25
IPV6_RECVPKTINFO = 49
IPV6_PKTINFO = 50
IPV6_RECVHOPLIMIT = 51
IPV6_HOPLIMIT = 52
IPV6_PATHMTU = 61
IPV6_DONTFRAG = 62

# PMTUD values.
IP_PMTUDISC_DO = 1

CMSG_ALIGNTO = struct.calcsize("@L")  # The kernel defines this as sizeof(long).

# Sendmsg flags
MSG_CONFIRM = 0X800
MSG_ERRQUEUE = 0x2000

# Linux errqueue API.
SO_ORIGIN_ICMP = 2
SO_ORIGIN_ICMP6 = 3

# Find the C library.
libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)


# TODO: Unlike most of this file, these functions aren't specific to wrapping C
# library calls. Move them to a utils.py or constants.py file, once we have one.
def LinuxVersion():
  # Example: "3.4.67-00753-gb7a556f", "4.4.135+".
  # Get the prefix consisting of digits and dots.
  version = re.search("^[0-9.]*", os.uname()[2]).group()
  # Convert it into a tuple such as (3, 4, 67). That allows comparing versions
  # using < and >, since tuples are compared lexicographically.
  version = tuple(int(i) for i in version.split("."))
  return version


def AddressVersion(addr):
  return 6 if ":" in addr else 4


def SetSocketTimeout(sock, ms):
  s = ms / 1000
  us = (ms % 1000) * 1000
  sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVTIMEO,
                  struct.pack("LL", s, us))


def VoidPointer(s):
  return ctypes.cast(s.CPointer(), ctypes.c_void_p)


def MaybeRaiseSocketError(ret):
  if ret < 0:
    errno = ctypes.get_errno()
    raise socket.error(errno, os.strerror(errno))


def Sockaddr(addr):
  if ":" in addr[0]:
    family = socket.AF_INET6
    if len(addr) == 4:
      addr, port, flowinfo, scope_id = addr
    else:
      (addr, port), flowinfo, scope_id = addr, 0, 0
    addr = socket.inet_pton(family, addr)
    return SockaddrIn6((family, socket.ntohs(port), socket.ntohl(flowinfo),
                        addr, scope_id))
  else:
    family = socket.AF_INET
    addr, port = addr
    addr = socket.inet_pton(family, addr)
    return SockaddrIn((family, socket.ntohs(port), addr))


def _MakeMsgControl(optlist):
  """Creates a msg_control blob from a list of cmsg attributes.

  Takes a list of cmsg attributes. Each attribute is a tuple of:
   - level: An integer, e.g., SOL_IPV6.
   - type: An integer, the option identifier, e.g., IPV6_HOPLIMIT.
   - data: The option data. This is either a string or an integer. If it's an
     integer it will be written as an unsigned integer in host byte order. If
     it's a string, it's used as is.

  Data is padded to an integer multiple of CMSG_ALIGNTO.

  Args:
    optlist: A list of tuples describing cmsg options.

  Returns:
    A string, a binary blob usable as the control data for a sendmsg call.

  Raises:
    TypeError: Option data is neither an integer nor a string.
  """
  msg_control = ""

  for i, opt in enumerate(optlist):
    msg_level, msg_type, data = opt
    if isinstance(data, int):
      data = struct.pack("=I", data)
    elif isinstance(data, ctypes.c_uint32):
      data = struct.pack("=I", data.value)
    elif not isinstance(data, str):
      raise TypeError("unknown data type for opt (%d, %d): %s" % (
          msg_level, msg_type, type(data)))

    datalen = len(data)
    msg_len = len(CMsgHdr) + datalen
    padding = "\x00" * util.GetPadLength(CMSG_ALIGNTO, datalen)
    msg_control += CMsgHdr((msg_len, msg_level, msg_type)).Pack()
    msg_control += data + padding

  return msg_control


def _ParseMsgControl(buf):
  """Parse a raw control buffer into a list of tuples."""
  msglist = []
  while len(buf) > 0:
    cmsghdr, buf = cstruct.Read(buf, CMsgHdr)
    datalen = cmsghdr.len - len(CMsgHdr)
    padlen = util.GetPadLength(CMSG_ALIGNTO, datalen)
    data, buf = buf[:datalen], buf[padlen + datalen:]

    if cmsghdr.level == socket.IPPROTO_IP:
      if cmsghdr.type == IP_PKTINFO:
        data = InPktinfo(data)
      elif cmsghdr.type == IP_TTL:
        data = struct.unpack("@I", data)[0]

    if cmsghdr.level == socket.IPPROTO_IPV6:
      if cmsghdr.type == IPV6_PKTINFO:
        data = In6Pktinfo(data)
      elif cmsghdr.type == IPV6_RECVERR:
        err, source = cstruct.Read(data, SockExtendedErr)
        if err.origin == SO_ORIGIN_ICMP6:
          source, pad = cstruct.Read(source, SockaddrIn6)
        data = (err, source)
      elif cmsghdr.type == IPV6_HOPLIMIT:
        data = struct.unpack("@I", data)[0]

    # If not, leave data as just the raw bytes.

    msglist.append((cmsghdr.level, cmsghdr.type, data))

  return msglist


def Bind(s, to):
  """Python wrapper for bind."""
  ret = libc.bind(s.fileno(), VoidPointer(to), len(to))
  MaybeRaiseSocketError(ret)
  return ret


def Connect(s, to):
  """Python wrapper for connect."""
  ret = libc.connect(s.fileno(), VoidPointer(to), len(to))
  MaybeRaiseSocketError(ret)
  return ret


def Sendmsg(s, to, data, control, flags):
  """Python wrapper for sendmsg.

  Args:
    s: A Python socket object. Becomes sockfd.
    to: An address tuple, or a SockaddrIn[6] struct. Becomes msg->msg_name.
    data: A string, the data to write. Goes into msg->msg_iov.
    control: A list of cmsg options. Becomes msg->msg_control.
    flags: An integer. Becomes msg->msg_flags.

  Returns:
    If sendmsg succeeds, returns the number of bytes written as an integer.

  Raises:
    socket.error: If sendmsg fails.
  """
  # Create ctypes buffers and pointers from our structures. We need to hang on
  # to the underlying Python objects, because we don't want them to be garbage
  # collected and freed while we have C pointers to them.

  # Convert the destination address into a struct sockaddr.
  if to:
    if isinstance(to, tuple):
      to = Sockaddr(to)
    msg_name = to.CPointer()
    msg_namelen = len(to)
  else:
    msg_name = 0
    msg_namelen = 0

  # Convert the data to a data buffer and a struct iovec pointing at it.
  if data:
    databuf = ctypes.create_string_buffer(data)
    iov = Iovec((ctypes.addressof(databuf), len(data)))
    msg_iov = iov.CPointer()
    msg_iovlen = 1
  else:
    msg_iov = 0
    msg_iovlen = 0

  # Marshal the cmsg options.
  if control:
    control = _MakeMsgControl(control)
    controlbuf = ctypes.create_string_buffer(control)
    msg_control = ctypes.addressof(controlbuf)
    msg_controllen = len(control)
  else:
    msg_control = 0
    msg_controllen = 0

  # Assemble the struct msghdr.
  msghdr = MsgHdr((msg_name, msg_namelen, msg_iov, msg_iovlen,
                   msg_control, msg_controllen, flags)).Pack()

  # Call sendmsg.
  ret = libc.sendmsg(s.fileno(), msghdr, 0)
  MaybeRaiseSocketError(ret)

  return ret


def _ToSocketAddress(addr, alen):
  addr = addr[:alen]

  # Attempt to convert the address to something we understand.
  if alen == 0:
    return None
  elif alen == len(SockaddrIn) and SockaddrIn(addr).family == socket.AF_INET:
    return SockaddrIn(addr)
  elif alen == len(SockaddrIn6) and SockaddrIn6(addr).family == socket.AF_INET6:
    return SockaddrIn6(addr)
  elif alen == len(SockaddrStorage):  # Can this ever happen?
    return SockaddrStorage(addr)
  else:
    return addr  # Unknown or malformed. Return the raw bytes.


def Recvmsg(s, buflen, controllen, flags, addrlen=len(SockaddrStorage)):
  """Python wrapper for recvmsg.

  Args:
    s: A Python socket object. Becomes sockfd.
    buflen: An integer, the maximum number of bytes to read.
    addrlen: An integer, the maximum size of the source address.
    controllen: An integer, the maximum size of the cmsg buffer.

  Returns:
    A tuple of received bytes, socket address tuple, and cmg list.

  Raises:
    socket.error: If recvmsg fails.
  """
  addr = ctypes.create_string_buffer(addrlen)
  msg_name = ctypes.addressof(addr)
  msg_namelen = addrlen

  buf = ctypes.create_string_buffer(buflen)
  iov = Iovec((ctypes.addressof(buf), buflen))
  msg_iov = iov.CPointer()
  msg_iovlen = 1

  control = ctypes.create_string_buffer(controllen)
  msg_control = ctypes.addressof(control)
  msg_controllen = controllen

  msghdr = MsgHdr((msg_name, msg_namelen, msg_iov, msg_iovlen,
                   msg_control, msg_controllen, flags))
  ret = libc.recvmsg(s.fileno(), VoidPointer(msghdr), flags)
  MaybeRaiseSocketError(ret)

  data = buf.raw[:ret]
  msghdr = MsgHdr(str(msghdr._buffer.raw))
  addr = _ToSocketAddress(addr, msghdr.namelen)
  control = control.raw[:msghdr.msg_controllen]
  msglist = _ParseMsgControl(control)

  return data, addr, msglist


def Recvfrom(s, size, flags=0):
  """Python wrapper for recvfrom."""
  buf = ctypes.create_string_buffer(size)
  addr = ctypes.create_string_buffer(len(SockaddrStorage))
  alen = ctypes.c_int(len(addr))

  ret = libc.recvfrom(s.fileno(), buf, len(buf), flags,
                      addr, ctypes.byref(alen))
  MaybeRaiseSocketError(ret)

  data = buf[:ret]
  alen = alen.value

  addr = _ToSocketAddress(addr.raw, alen)

  return data, addr


def Setsockopt(s, level, optname, optval, optlen):
  """Python wrapper for setsockopt.

  Mostly identical to the built-in setsockopt, but allows passing in arbitrary
  binary blobs, including NULL options, which the built-in python setsockopt does
  not allow.

  Args:
    s: The socket object on which to set the option.
    level: The level parameter.
    optname: The option to set.
    optval: A raw byte string, the value to set the option to (None for NULL).
    optlen: An integer, the length of the option.

  Raises:
    socket.error: if setsockopt fails.
  """
  ret = libc.setsockopt(s.fileno(), level, optname, optval, optlen)
  MaybeRaiseSocketError(ret)
