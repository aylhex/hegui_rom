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

import time
from socket import *  # pylint: disable=wildcard-import

import net_test
import multinetwork_base
import packets

# TCP states. See include/net/tcp_states.h.
TCP_ESTABLISHED = 1
TCP_SYN_SENT = 2
TCP_SYN_RECV = 3
TCP_FIN_WAIT1 = 4
TCP_FIN_WAIT2 = 5
TCP_TIME_WAIT = 6
TCP_CLOSE = 7
TCP_CLOSE_WAIT = 8
TCP_LAST_ACK = 9
TCP_LISTEN = 10
TCP_CLOSING = 11
TCP_NEW_SYN_RECV = 12

TCP_NOT_YET_ACCEPTED = -1


class TcpBaseTest(multinetwork_base.MultiNetworkBaseTest):

  def tearDown(self):
    if hasattr(self, "s"):
      self.s.close()
    super(TcpBaseTest, self).tearDown()

  def OpenListenSocket(self, version, netid):
    family = {4: AF_INET, 5: AF_INET6, 6: AF_INET6}[version]
    address = {4: "0.0.0.0", 5: "::", 6: "::"}[version]
    s = net_test.Socket(family, SOCK_STREAM, IPPROTO_TCP)
    # We haven't configured inbound iptables marking, so bind explicitly.
    self.SelectInterface(s, netid, "mark")
    self.port = net_test.BindRandomPort(version, s)
    return s

  def _ReceiveAndExpectResponse(self, netid, packet, reply, msg):
    pkt = super(TcpBaseTest, self)._ReceiveAndExpectResponse(netid, packet,
                                                             reply, msg)
    self.last_packet = pkt
    return pkt

  def ReceivePacketOn(self, netid, packet):
    super(TcpBaseTest, self).ReceivePacketOn(netid, packet)
    self.last_packet = packet

  def ReceiveRstPacketOn(self, netid):
    # self.last_packet is the last packet we received. Invert direction twice.
    _, ack = packets.ACK(self.version, self.myaddr, self.remoteaddr,
                         self.last_packet)
    desc, rst = packets.RST(self.version, self.remoteaddr, self.myaddr,
                            ack)
    super(TcpBaseTest, self).ReceivePacketOn(netid, rst)

  def RstPacket(self):
    return packets.RST(self.version, self.myaddr, self.remoteaddr,
                       self.last_packet)

  def FinPacket(self):
    return packets.FIN(self.version, self.myaddr, self.remoteaddr,
                       self.last_packet)


  def IncomingConnection(self, version, end_state, netid):
    self.s = self.OpenListenSocket(version, netid)
    self.end_state = end_state

    remoteaddr = self.remoteaddr = self.GetRemoteAddress(version)
    remotesockaddr = self.remotesockaddr = self.GetRemoteSocketAddress(version)

    myaddr = self.myaddr = self.MyAddress(version, netid)
    mysockaddr = self.mysockaddr = self.MySocketAddress(version, netid)

    if version == 5: version = 4
    self.version = version

    if end_state == TCP_LISTEN:
      return

    desc, syn = packets.SYN(self.port, version, remoteaddr, myaddr)
    synack_desc, synack = packets.SYNACK(version, myaddr, remoteaddr, syn)
    msg = "Received %s, expected to see reply %s" % (desc, synack_desc)
    reply = self._ReceiveAndExpectResponse(netid, syn, synack, msg)
    if end_state == TCP_SYN_RECV:
      return

    establishing_ack = packets.ACK(version, remoteaddr, myaddr, reply)[1]
    self.ReceivePacketOn(netid, establishing_ack)

    if end_state == TCP_NOT_YET_ACCEPTED:
      return

    self.accepted, _ = self.s.accept()
    net_test.DisableFinWait(self.accepted)

    if end_state == TCP_ESTABLISHED:
      return

    desc, data = packets.ACK(version, myaddr, remoteaddr, establishing_ack,
                             payload=net_test.UDP_PAYLOAD)
    self.accepted.send(net_test.UDP_PAYLOAD)
    self.ExpectPacketOn(netid, msg + ": expecting %s" % desc, data)

    desc, fin = packets.FIN(version, remoteaddr, myaddr, data)
    fin = packets._GetIpLayer(version)(str(fin))
    ack_desc, ack = packets.ACK(version, myaddr, remoteaddr, fin)
    msg = "Received %s, expected to see reply %s" % (desc, ack_desc)

    # TODO: Why can't we use this?
    #   self._ReceiveAndExpectResponse(netid, fin, ack, msg)
    self.ReceivePacketOn(netid, fin)
    time.sleep(0.1)
    self.ExpectPacketOn(netid, msg + ": expecting %s" % ack_desc, ack)
    if end_state == TCP_CLOSE_WAIT:
      return

    raise ValueError("Invalid TCP state %d specified" % end_state)
