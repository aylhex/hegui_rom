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

"""Partial implementation of the PFKEYv2 interface."""

# pylint: disable=g-bad-todo,bad-whitespace

import os
from socket import *  # pylint: disable=wildcard-import
import sys

import cstruct
import net_test


# AF_KEY socket type. See include/linux/socket.h.
AF_KEY = 15

# PFKEYv2 constants. See include/uapi/linux/pfkeyv2.h.
PF_KEY_V2 = 2

# IPsec constants. See include/uapi/linux/ipsec.h.
IPSEC_MODE_ANY       = 0
IPSEC_MODE_TRANSPORT = 1
IPSEC_MODE_TUNNEL    = 2
IPSEC_MODE_BEET      = 3

# Operation types.
SADB_ADD = 3
SADB_DELETE = 4
SADB_DUMP = 10

# SA types.
SADB_TYPE_UNSPEC = 0
SADB_TYPE_AH = 2
SADB_TYPE_ESP = 3

# SA states.
SADB_SASTATE_LARVAL = 0
SADB_SASTATE_MATURE = 1
SADB_SASTATE_DYING  = 2
SADB_SASTATE_DEAD   = 3

# Authentication algorithms.
SADB_AALG_NONE            = 0
SADB_AALG_MD5HMAC         = 2
SADB_AALG_SHA1HMAC        = 3
SADB_X_AALG_SHA2_256HMAC  = 5
SADB_X_AALG_SHA2_384HMAC  = 6
SADB_X_AALG_SHA2_512HMAC  = 7
SADB_X_AALG_RIPEMD160HMAC = 8
SADB_X_AALG_AES_XCBC_MAC  = 9
SADB_X_AALG_NULL          = 251

# Encryption algorithms.
SADB_EALG_NONE            = 0
SADB_EALG_DESCBC          = 2
SADB_EALG_3DESCBC         = 3
SADB_X_EALG_CASTCBC       = 6
SADB_X_EALG_BLOWFISHCBC   = 7
SADB_EALG_NULL            = 11
SADB_X_EALG_AESCBC        = 12
SADB_X_EALG_AESCTR        = 13
SADB_X_EALG_AES_CCM_ICV8  = 14
SADB_X_EALG_AES_CCM_ICV12 = 15
SADB_X_EALG_AES_CCM_ICV16 = 16
SADB_X_EALG_AES_GCM_ICV8  = 18
SADB_X_EALG_AES_GCM_ICV12 = 19
SADB_X_EALG_AES_GCM_ICV16 = 20
SADB_X_EALG_CAMELLIACBC   = 22
SADB_X_EALG_NULL_AES_GMAC = 23
SADB_X_EALG_SERPENTCBC    = 252
SADB_X_EALG_TWOFISHCBC    = 253

# Extension Header values.
SADB_EXT_RESERVED          = 0
SADB_EXT_SA                = 1
SADB_EXT_LIFETIME_CURRENT  = 2
SADB_EXT_LIFETIME_HARD     = 3
SADB_EXT_LIFETIME_SOFT     = 4
SADB_EXT_ADDRESS_SRC       = 5
SADB_EXT_ADDRESS_DST       = 6
SADB_EXT_ADDRESS_PROXY     = 7
SADB_EXT_KEY_AUTH          = 8
SADB_EXT_KEY_ENCRYPT       = 9
SADB_EXT_IDENTITY_SRC      = 10
SADB_EXT_IDENTITY_DST      = 11
SADB_EXT_SENSITIVITY       = 12
SADB_EXT_PROPOSAL          = 13
SADB_EXT_SUPPORTED_AUTH    = 14
SADB_EXT_SUPPORTED_ENCRYPT = 15
SADB_EXT_SPIRANGE          =  16
SADB_X_EXT_KMPRIVATE       = 17
SADB_X_EXT_POLICY          = 18
SADB_X_EXT_SA2             = 19
SADB_X_EXT_NAT_T_TYPE      = 20
SADB_X_EXT_NAT_T_SPORT     = 21
SADB_X_EXT_NAT_T_DPORT     = 22
SADB_X_EXT_NAT_T_OA        = 23
SADB_X_EXT_SEC_CTX         = 24
SADB_X_EXT_KMADDRESS       = 25
SADB_X_EXT_FILTER          = 26

# Data structure formats.
# These aren't constants, they're classes. So, pylint: disable=invalid-name
SadbMsg = cstruct.Struct(
    "SadbMsg", "=BBBBHHII", "version type errno satype len reserved seq pid")

# Fake struct containing the common beginning of all extension structs.
SadbExt = cstruct.Struct("SadbExt", "=HH", "len exttype")

SadbSa = cstruct.Struct(
    "SadbSa", "=IBBBBI", "spi replay state auth encrypt flags")

SadbLifetime = cstruct.Struct(
    "SadbLifetime", "=IQQQ", "allocations bytes addtime usetime")

SadbAddress = cstruct.Struct("SadbAddress", "=BB2x", "proto prefixlen")

SadbKey = cstruct.Struct("SadbKey", "=H2x", "bits")

SadbXSa2 = cstruct.Struct("SadbXSa2", "=B3xII", "mode sequence reqid")

SadbXNatTType = cstruct.Struct("SadbXNatTType", "=B3x", "type")

SadbXNatTPort = cstruct.Struct("SadbXNatTPort", "!H2x", "port")


def _GetConstantName(value, prefix):
  """Translates a number to a constant of the same value in this file."""
  thismodule = sys.modules[__name__]
  # Match shorter constant names first. This allows us to match SADB_DUMP and
  # instead of, say, SADB_EXT_LIFETIME_HARD if we pass in a prefix of "SADB_"
  # and a value of 3, and match SADB_EXT_LIFETIME_HARD just by specifying
  # a longer prefix.
  for name in sorted(dir(thismodule), key=len):
    if (name.startswith(prefix) and
        name.isupper() and getattr(thismodule, name) == value):
      return name
  return value


def _GetMultiConstantName(value, prefixes):
  for prefix in prefixes:
    name = _GetConstantName(value, prefix)
    try:
      int(name)
      continue
    except ValueError:
      return name


# Converts extension blobs to a (name, struct, attrs) tuple.
def ParseExtension(exttype, data):
  struct_type = None
  if exttype == SADB_EXT_SA:
    struct_type = SadbSa
  elif exttype in [SADB_EXT_LIFETIME_CURRENT, SADB_EXT_LIFETIME_HARD,
                   SADB_EXT_LIFETIME_SOFT]:
    struct_type = SadbLifetime
  elif exttype in [SADB_EXT_ADDRESS_SRC, SADB_EXT_ADDRESS_DST,
                   SADB_EXT_ADDRESS_PROXY]:
    struct_type = SadbAddress
  elif exttype in [SADB_EXT_KEY_AUTH, SADB_EXT_KEY_ENCRYPT]:
    struct_type = SadbKey
  elif exttype == SADB_X_EXT_SA2:
    struct_type = SadbXSa2
  elif exttype == SADB_X_EXT_NAT_T_TYPE:
    struct_type = SadbXNatTType
  elif exttype in [SADB_X_EXT_NAT_T_SPORT, SADB_X_EXT_NAT_T_DPORT]:
    struct_type = SadbXNatTPort

  if struct_type:
    ext, attrs = cstruct.Read(data, struct_type)
  else:
    ext, attrs, = data, ""

  return exttype, ext, attrs

class PfKey(object):

  """PF_KEY interface to kernel IPsec implementation."""

  def __init__(self):
    self.sock = socket(AF_KEY, SOCK_RAW, PF_KEY_V2)
    net_test.SetNonBlocking(self.sock)
    self.seq = 0

  def Recv(self):
    reply = self.sock.recv(4096)
    msg = SadbMsg(reply)
    # print "RECV:", self.DecodeSadbMsg(msg)
    if msg.errno != 0:
      raise OSError(msg.errno, os.strerror(msg.errno))
    return reply

  def SendAndRecv(self, msg, extensions):
    self.seq += 1
    msg.seq = self.seq
    msg.pid = os.getpid()
    msg.len = (len(SadbMsg) + len(extensions)) / 8
    self.sock.send(msg.Pack() + extensions)
    # print "SEND:", self.DecodeSadbMsg(msg)
    return self.Recv()

  def PackPfKeyExtensions(self, extlist):
    extensions = ""
    for exttype, extstruct, attrs in extlist:
      extdata = extstruct.Pack()
      ext = SadbExt(((len(extdata) + len(SadbExt) + len(attrs)) / 8, exttype))
      extensions += ext.Pack() + extdata + attrs
    return extensions

  def MakeSadbMsg(self, msgtype, satype):
    # errno is 0. seq, pid and len are filled in by SendAndRecv().
    return SadbMsg((PF_KEY_V2, msgtype, 0, satype, 0, 0, 0, 0))

  def MakeSadbExtAddr(self, exttype, addr):
    prefixlen = {AF_INET: 32, AF_INET6: 128}[addr.family]
    packed = addr.Pack()
    padbytes = (len(SadbExt) + len(SadbAddress) + len(packed)) % 8
    packed += "\x00" * padbytes
    return (exttype, SadbAddress((0, prefixlen)), packed)

  def AddSa(self, src, dst, spi, satype, mode, reqid, encryption,
            encryption_key, auth, auth_key):
    """Adds a security association."""
    msg = self.MakeSadbMsg(SADB_ADD, satype)
    replay = 4
    extlist = [
        (SADB_EXT_SA, SadbSa((htonl(spi), replay, SADB_SASTATE_MATURE,
                              auth, encryption, 0)), ""),
        self.MakeSadbExtAddr(SADB_EXT_ADDRESS_SRC, src),
        self.MakeSadbExtAddr(SADB_EXT_ADDRESS_DST, dst),
        (SADB_X_EXT_SA2, SadbXSa2((mode, 0, reqid)), ""),
        (SADB_EXT_KEY_AUTH, SadbKey((len(auth_key) * 8,)), auth_key),
        (SADB_EXT_KEY_ENCRYPT, SadbKey((len(encryption_key) * 8,)),
         encryption_key)
    ]
    self.SendAndRecv(msg, self.PackPfKeyExtensions(extlist))

  def DelSa(self, src, dst, spi, satype):
    """Deletes a security association."""
    msg = self.MakeSadbMsg(SADB_DELETE, satype)
    extlist = [
        (SADB_EXT_SA, SadbSa((htonl(spi), 4, SADB_SASTATE_MATURE,
                              0, 0, 0)), ""),
        self.MakeSadbExtAddr(SADB_EXT_ADDRESS_SRC, src),
        self.MakeSadbExtAddr(SADB_EXT_ADDRESS_DST, dst),
    ]
    self.SendAndRecv(msg, self.PackPfKeyExtensions(extlist))

  @staticmethod
  def DecodeSadbMsg(msg):
    msgtype = _GetConstantName(msg.type, "SADB_")
    satype = _GetConstantName(msg.satype, "SADB_TYPE_")
    return ("SadbMsg(version=%d, type=%s, errno=%d, satype=%s, "
            "len=%d, reserved=%d, seq=%d, pid=%d)" % (
                msg.version, msgtype, msg.errno, satype, msg.len,
                msg.reserved, msg.seq, msg.pid))

  @staticmethod
  def DecodeSadbSa(sa):
    state = _GetConstantName(sa.state, "SADB_SASTATE_")
    auth = _GetMultiConstantName(sa.auth, ["SADB_AALG_", "SADB_X_AALG"])
    encrypt = _GetMultiConstantName(sa.encrypt, ["SADB_EALG_",
                                                 "SADB_X_EALG_"])
    return ("SadbSa(spi=%x, replay=%d, state=%s, "
            "auth=%s, encrypt=%s, flags=%x)" % (
                sa.spi, sa.replay, state, auth, encrypt, sa.flags))

  @staticmethod
  def ExtensionsLength(msg, struct_type):
    return (msg.len * 8) - len(struct_type)

  @staticmethod
  def ParseExtensions(data):
    """Parses the extensions in a SADB message."""
    extensions = []
    while data:
      ext, data = cstruct.Read(data, SadbExt)
      datalen = PfKey.ExtensionsLength(ext, SadbExt)
      extdata, data = data[:datalen], data[datalen:]
      extensions.append(ParseExtension(ext.exttype, extdata))
    return extensions

  def DumpSaInfo(self):
    """Returns a list of (SadbMsg, [(extension, attr), ...], ...) tuples."""
    dump = []
    msg = self.MakeSadbMsg(SADB_DUMP, SADB_TYPE_UNSPEC)
    received = self.SendAndRecv(msg, "")
    while received:
      msg, data = cstruct.Read(received, SadbMsg)
      extlen = self.ExtensionsLength(msg, SadbMsg)
      extensions, data = data[:extlen], data[extlen:]
      dump.append((msg, self.ParseExtensions(extensions)))
      if msg.seq == 0:  # End of dump.
        break
      received = self.Recv()
    return dump

  def PrintSaInfos(self, dump):
    for msg, extensions in dump:
      print self.DecodeSadbMsg(msg)
      for exttype, ext, attrs in extensions:
        exttype = _GetMultiConstantName(exttype, ["SADB_EXT", "SADB_X_EXT"])
        if exttype == SADB_EXT_SA:
          print " ", exttype, self.DecodeSadbSa(ext), attrs.encode("hex")
        print " ", exttype, ext, attrs.encode("hex")
      print


if __name__ == "__main__":
  p = PfKey()
  p.DumpSaInfo()
