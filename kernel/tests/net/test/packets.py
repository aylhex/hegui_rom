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

import random

from scapy import all as scapy
from socket import *

import net_test

TCP_FIN = 1
TCP_SYN = 2
TCP_RST = 4
TCP_PSH = 8
TCP_ACK = 16

TCP_WINDOW = 14400

PTB_MTU = 1280

PING_IDENT = 0xff19
PING_PAYLOAD = "foobarbaz"
PING_SEQ = 3
PING_TOS = 0x83

# For brevity.
UDP_PAYLOAD = net_test.UDP_PAYLOAD


def _RandomPort():
  return random.randint(1025, 65535)

def _GetIpLayer(version):
  return {4: scapy.IP, 5: scapy.IP, 6: scapy.IPv6}[version]

def _SetPacketTos(packet, tos):
  if isinstance(packet, scapy.IPv6):
    packet.tc = tos
  elif isinstance(packet, scapy.IP):
    packet.tos = tos
  else:
    raise ValueError("Can't find ToS Field")

def UDP(version, srcaddr, dstaddr, sport=0):
  ip = _GetIpLayer(version)
  # Can't just use "if sport" because None has meaning (it means unspecified).
  if sport == 0:
    sport = _RandomPort()
  return ("UDPv%d packet" % version,
          ip(src=srcaddr, dst=dstaddr) /
          scapy.UDP(sport=sport, dport=53) / UDP_PAYLOAD)

def UDPWithOptions(version, srcaddr, dstaddr, sport=0, lifetime=39):
  if version == 4:
    packet = (scapy.IP(src=srcaddr, dst=dstaddr, ttl=lifetime, tos=0x83) /
              scapy.UDP(sport=sport, dport=53) /
              UDP_PAYLOAD)
  else:
    packet = (scapy.IPv6(src=srcaddr, dst=dstaddr,
                         fl=0xbeef, hlim=lifetime, tc=0x83) /
              scapy.UDP(sport=sport, dport=53) /
              UDP_PAYLOAD)
  return ("UDPv%d packet with options" % version, packet)

def SYN(dport, version, srcaddr, dstaddr, sport=0, seq=-1):
  ip = _GetIpLayer(version)
  if sport == 0:
    sport = _RandomPort()
  if seq == -1:  # Can't use None because it means unspecified.
    seq = random.getrandbits(32)
  return ("TCP SYN",
          ip(src=srcaddr, dst=dstaddr) /
          scapy.TCP(sport=sport, dport=dport,
                    seq=seq, ack=0,
                    flags=TCP_SYN, window=TCP_WINDOW))

def RST(version, srcaddr, dstaddr, packet):
  ip = _GetIpLayer(version)
  original = packet.getlayer("TCP")
  was_syn_or_fin = (original.flags & (TCP_SYN | TCP_FIN)) != 0
  return ("TCP RST",
          ip(src=srcaddr, dst=dstaddr) /
          scapy.TCP(sport=original.dport, dport=original.sport,
                    ack=original.seq + was_syn_or_fin,
                    seq=original.ack,
                    flags=TCP_RST | TCP_ACK, window=TCP_WINDOW))

def SYNACK(version, srcaddr, dstaddr, packet):
  ip = _GetIpLayer(version)
  original = packet.getlayer("TCP")
  return ("TCP SYN+ACK",
          ip(src=srcaddr, dst=dstaddr) /
          scapy.TCP(sport=original.dport, dport=original.sport,
                    ack=original.seq + 1, seq=None,
                    flags=TCP_SYN | TCP_ACK, window=None))

def ACK(version, srcaddr, dstaddr, packet, payload=""):
  ip = _GetIpLayer(version)
  original = packet.getlayer("TCP")
  was_syn_or_fin = (original.flags & (TCP_SYN | TCP_FIN)) != 0
  ack_delta = was_syn_or_fin + len(original.payload)
  desc = "TCP data" if payload else "TCP ACK"
  flags = TCP_ACK | TCP_PSH if payload else TCP_ACK
  return (desc,
          ip(src=srcaddr, dst=dstaddr) /
          scapy.TCP(sport=original.dport, dport=original.sport,
                    ack=original.seq + ack_delta, seq=original.ack,
                    flags=flags, window=TCP_WINDOW) /
          payload)

def FIN(version, srcaddr, dstaddr, packet):
  ip = _GetIpLayer(version)
  original = packet.getlayer("TCP")
  was_syn_or_fin = (original.flags & (TCP_SYN | TCP_FIN)) != 0
  ack_delta = was_syn_or_fin + len(original.payload)
  return ("TCP FIN",
          ip(src=srcaddr, dst=dstaddr) /
          scapy.TCP(sport=original.dport, dport=original.sport,
                    ack=original.seq + ack_delta, seq=original.ack,
                    flags=TCP_ACK | TCP_FIN, window=TCP_WINDOW))

def GRE(version, srcaddr, dstaddr, proto, packet):
  if version == 4:
    ip = scapy.IP(src=srcaddr, dst=dstaddr, proto=net_test.IPPROTO_GRE)
  else:
    ip = scapy.IPv6(src=srcaddr, dst=dstaddr, nh=net_test.IPPROTO_GRE)
  packet = ip / scapy.GRE(proto=proto) / packet
  return ("GRE packet", packet)

def ICMPPortUnreachable(version, srcaddr, dstaddr, packet):
  if version == 4:
    # Linux hardcodes the ToS on ICMP errors to 0xc0 or greater because of
    # RFC 1812 4.3.2.5 (!).
    return ("ICMPv4 port unreachable",
            scapy.IP(src=srcaddr, dst=dstaddr, proto=1, tos=0xc0) /
            scapy.ICMPerror(type=3, code=3) / packet)
  else:
    return ("ICMPv6 port unreachable",
            scapy.IPv6(src=srcaddr, dst=dstaddr) /
            scapy.ICMPv6DestUnreach(code=4) / packet)

def ICMPPacketTooBig(version, srcaddr, dstaddr, packet):
  if version == 4:
    desc = "ICMPv4 fragmentation needed"
    pkt = (scapy.IP(src=srcaddr, dst=dstaddr, proto=1) /
           scapy.ICMPerror(type=3, code=4) / str(packet)[:64])
    # Only newer versions of scapy understand that since RFC 1191, the last two
    # bytes of a fragmentation needed ICMP error contain the MTU.
    if hasattr(scapy.ICMP, "nexthopmtu"):
      pkt[scapy.ICMPerror].nexthopmtu = PTB_MTU
    else:
      pkt[scapy.ICMPerror].unused = PTB_MTU
    return desc, pkt
  else:
    return ("ICMPv6 Packet Too Big",
            scapy.IPv6(src=srcaddr, dst=dstaddr) /
            scapy.ICMPv6PacketTooBig(mtu=PTB_MTU) / str(packet)[:1232])

def ICMPEcho(version, srcaddr, dstaddr):
  ip = _GetIpLayer(version)
  icmp = {4: scapy.ICMP, 6: scapy.ICMPv6EchoRequest}[version]
  packet = (ip(src=srcaddr, dst=dstaddr) /
            icmp(id=PING_IDENT, seq=PING_SEQ) / PING_PAYLOAD)
  _SetPacketTos(packet, PING_TOS)
  return ("ICMPv%d echo" % version, packet)

def ICMPReply(version, srcaddr, dstaddr, packet):
  ip = _GetIpLayer(version)
  # Scapy doesn't provide an ICMP echo reply constructor.
  icmpv4_reply = lambda **kwargs: scapy.ICMP(type=0, **kwargs)
  icmp = {4: icmpv4_reply, 6: scapy.ICMPv6EchoReply}[version]
  packet = (ip(src=srcaddr, dst=dstaddr) /
            icmp(id=PING_IDENT, seq=PING_SEQ) / PING_PAYLOAD)
  # IPv6 only started copying the tclass to echo replies in 3.14.
  if version == 4 or net_test.LINUX_VERSION >= (3, 14):
    _SetPacketTos(packet, PING_TOS)
  return ("ICMPv%d echo reply" % version, packet)

def NS(srcaddr, tgtaddr, srcmac):
  solicited = inet_pton(AF_INET6, tgtaddr)
  last3bytes = tuple([ord(b) for b in solicited[-3:]])
  solicited = "ff02::1:ff%02x:%02x%02x" % last3bytes
  packet = (scapy.IPv6(src=srcaddr, dst=solicited) /
            scapy.ICMPv6ND_NS(tgt=tgtaddr) /
            scapy.ICMPv6NDOptSrcLLAddr(lladdr=srcmac))
  return ("ICMPv6 NS", packet)

def NA(srcaddr, dstaddr, srcmac):
  packet = (scapy.IPv6(src=srcaddr, dst=dstaddr) /
            scapy.ICMPv6ND_NA(tgt=srcaddr, R=0, S=1, O=1) /
            scapy.ICMPv6NDOptDstLLAddr(lladdr=srcmac))
  return ("ICMPv6 NA", packet)

