#!/usr/bin/python
#
# Copyright 2019 The Android Open Source Project
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

import unittest

from errno import *  # pylint: disable=wildcard-import
from socket import *  # pylint: disable=wildcard-import
import ctypes
import fcntl
import os
import random
import select
import termios
import threading
import time
from scapy import all as scapy

import multinetwork_base
import net_test
import packets

SOL_TCP = net_test.SOL_TCP
SHUT_RD = net_test.SHUT_RD
SHUT_WR = net_test.SHUT_WR
SHUT_RDWR = net_test.SHUT_RDWR
SIOCINQ = termios.FIONREAD
SIOCOUTQ = termios.TIOCOUTQ

TEST_PORT = 5555

# Following constants are SOL_TCP level options and arguments.
# They are defined in linux-kernel: include/uapi/linux/tcp.h

# SOL_TCP level options.
TCP_REPAIR = 19
TCP_REPAIR_QUEUE = 20
TCP_QUEUE_SEQ = 21

# TCP_REPAIR_{OFF, ON} is an argument to TCP_REPAIR.
TCP_REPAIR_OFF = 0
TCP_REPAIR_ON = 1

# TCP_{NO, RECV, SEND}_QUEUE is an argument to TCP_REPAIR_QUEUE.
TCP_NO_QUEUE = 0
TCP_RECV_QUEUE = 1
TCP_SEND_QUEUE = 2

# This test is aiming to ensure tcp keep alive offload works correctly
# when it fetches tcp information from kernel via tcp repair mode.
class TcpRepairTest(multinetwork_base.MultiNetworkBaseTest):

  def assertSocketNotConnected(self, sock):
    self.assertRaisesErrno(ENOTCONN, sock.getpeername)

  def assertSocketConnected(self, sock):
    sock.getpeername()  # No errors? Socket is alive and connected.

  def createConnectedSocket(self, version, netid):
    s = net_test.TCPSocket(net_test.GetAddressFamily(version))
    net_test.DisableFinWait(s)
    self.SelectInterface(s, netid, "mark")

    remotesockaddr = self.GetRemoteSocketAddress(version)
    remoteaddr = self.GetRemoteAddress(version)
    self.assertRaisesErrno(EINPROGRESS, s.connect, (remotesockaddr, TEST_PORT))
    self.assertSocketNotConnected(s)

    myaddr = self.MyAddress(version, netid)
    port = s.getsockname()[1]
    self.assertNotEqual(0, port)

    desc, expect_syn = packets.SYN(TEST_PORT, version, myaddr, remoteaddr, port, seq=None)
    msg = "socket connect: expected %s" % desc
    syn = self.ExpectPacketOn(netid, msg, expect_syn)
    synack_desc, synack = packets.SYNACK(version, remoteaddr, myaddr, syn)
    synack.getlayer("TCP").seq = random.getrandbits(32)
    synack.getlayer("TCP").window = 14400
    self.ReceivePacketOn(netid, synack)
    desc, ack = packets.ACK(version, myaddr, remoteaddr, synack)
    msg = "socket connect: got SYN+ACK, expected %s" % desc
    ack = self.ExpectPacketOn(netid, msg, ack)
    self.last_sent = ack
    self.last_received = synack
    return s

  def receiveFin(self, netid, version, sock):
    self.assertSocketConnected(sock)
    remoteaddr = self.GetRemoteAddress(version)
    myaddr = self.MyAddress(version, netid)
    desc, fin = packets.FIN(version, remoteaddr, myaddr, self.last_sent)
    self.ReceivePacketOn(netid, fin)
    self.last_received = fin

  def sendData(self, netid, version, sock, payload):
    sock.send(payload)

    remoteaddr = self.GetRemoteAddress(version)
    myaddr = self.MyAddress(version, netid)
    desc, send = packets.ACK(version, myaddr, remoteaddr,
                             self.last_received, payload)
    self.last_sent = send

  def receiveData(self, netid, version, payload):
    remoteaddr = self.GetRemoteAddress(version)
    myaddr = self.MyAddress(version, netid)

    desc, received = packets.ACK(version, remoteaddr, myaddr,
                                 self.last_sent, payload)
    ack_desc, ack = packets.ACK(version, myaddr, remoteaddr, received)
    self.ReceivePacketOn(netid, received)
    time.sleep(0.1)
    self.ExpectPacketOn(netid, "expecting %s" % ack_desc, ack)
    self.last_sent = ack
    self.last_received = received

  # Test the behavior of NO_QUEUE. Expect incoming data will be stored into
  # the queue, but socket cannot be read/written in NO_QUEUE.
  def testTcpRepairInNoQueue(self):
    for version in [4, 5, 6]:
      self.tcpRepairInNoQueueTest(version)

  def tcpRepairInNoQueueTest(self, version):
    netid = self.RandomNetid()
    sock = self.createConnectedSocket(version, netid)
    sock.setsockopt(SOL_TCP, TCP_REPAIR, TCP_REPAIR_ON)

    # In repair mode with NO_QUEUE, writes fail...
    self.assertRaisesErrno(EINVAL, sock.send, "write test")

    # remote data is coming.
    TEST_RECEIVED = net_test.UDP_PAYLOAD
    self.receiveData(netid, version, TEST_RECEIVED)

    # In repair mode with NO_QUEUE, read fail...
    self.assertRaisesErrno(EPERM, sock.recv, 4096)

    sock.setsockopt(SOL_TCP, TCP_REPAIR, TCP_REPAIR_OFF)
    readData = sock.recv(4096)
    self.assertEquals(readData, TEST_RECEIVED)
    sock.close()

  # Test whether tcp read/write sequence number can be fetched correctly
  # by TCP_QUEUE_SEQ.
  def testGetSequenceNumber(self):
    for version in [4, 5, 6]:
      self.GetSequenceNumberTest(version)

  def GetSequenceNumberTest(self, version):
    netid = self.RandomNetid()
    sock = self.createConnectedSocket(version, netid)
    # test write queue sequence number
    sequence_before = self.GetWriteSequenceNumber(version, sock)
    expect_sequence = self.last_sent.getlayer("TCP").seq
    self.assertEquals(sequence_before & 0xffffffff, expect_sequence)
    TEST_SEND = net_test.UDP_PAYLOAD
    self.sendData(netid, version, sock, TEST_SEND)
    sequence_after = self.GetWriteSequenceNumber(version, sock)
    self.assertEquals(sequence_before + len(TEST_SEND), sequence_after)

    # test read queue sequence number
    sequence_before = self.GetReadSequenceNumber(version, sock)
    expect_sequence = self.last_received.getlayer("TCP").seq + 1
    self.assertEquals(sequence_before & 0xffffffff, expect_sequence)
    TEST_READ = net_test.UDP_PAYLOAD
    self.receiveData(netid, version, TEST_READ)
    sequence_after = self.GetReadSequenceNumber(version, sock)
    self.assertEquals(sequence_before + len(TEST_READ), sequence_after)
    sock.close()

  def GetWriteSequenceNumber(self, version, sock):
    sock.setsockopt(SOL_TCP, TCP_REPAIR, TCP_REPAIR_ON)
    sock.setsockopt(SOL_TCP, TCP_REPAIR_QUEUE, TCP_SEND_QUEUE)
    sequence = sock.getsockopt(SOL_TCP, TCP_QUEUE_SEQ)
    sock.setsockopt(SOL_TCP, TCP_REPAIR_QUEUE, TCP_NO_QUEUE)
    sock.setsockopt(SOL_TCP, TCP_REPAIR, TCP_REPAIR_OFF)
    return sequence

  def GetReadSequenceNumber(self, version, sock):
    sock.setsockopt(SOL_TCP, TCP_REPAIR, TCP_REPAIR_ON)
    sock.setsockopt(SOL_TCP, TCP_REPAIR_QUEUE, TCP_RECV_QUEUE)
    sequence = sock.getsockopt(SOL_TCP, TCP_QUEUE_SEQ)
    sock.setsockopt(SOL_TCP, TCP_REPAIR_QUEUE, TCP_NO_QUEUE)
    sock.setsockopt(SOL_TCP, TCP_REPAIR, TCP_REPAIR_OFF)
    return sequence

  # Test whether tcp repair socket can be poll()'ed correctly
  # in mutiple threads at the same time.
  def testMultiThreadedPoll(self):
    for version in [4, 5, 6]:
      self.PollWhenShutdownTest(version)
      self.PollWhenReceiveFinTest(version)

  def PollRepairSocketInMultipleThreads(self, netid, version, expected):
    sock = self.createConnectedSocket(version, netid)
    sock.setsockopt(SOL_TCP, TCP_REPAIR, TCP_REPAIR_ON)

    multiThreads = []
    for i in [0, 1]:
      thread = SocketExceptionThread(sock, lambda sk: self.fdSelect(sock, expected))
      thread.start()
      self.assertTrue(thread.is_alive())
      multiThreads.append(thread)

    return sock, multiThreads

  def assertThreadsStopped(self, multiThreads, msg) :
    for thread in multiThreads:
      if (thread.is_alive()):
        thread.join(1)
      if (thread.is_alive()):
        thread.stop()
        raise AssertionError(msg)

  def PollWhenShutdownTest(self, version):
    netid = self.RandomNetid()
    expected = select.POLLIN
    sock, multiThreads = self.PollRepairSocketInMultipleThreads(netid, version, expected)
    # Test shutdown RD.
    sock.shutdown(SHUT_RD)
    self.assertThreadsStopped(multiThreads, "poll fail during SHUT_RD")
    sock.close()

    expected = None
    sock, multiThreads = self.PollRepairSocketInMultipleThreads(netid, version, expected)
    # Test shutdown WR.
    sock.shutdown(SHUT_WR)
    self.assertThreadsStopped(multiThreads, "poll fail during SHUT_WR")
    sock.close()

    expected = select.POLLIN | select.POLLHUP
    sock, multiThreads = self.PollRepairSocketInMultipleThreads(netid, version, expected)
    # Test shutdown RDWR.
    sock.shutdown(SHUT_RDWR)
    self.assertThreadsStopped(multiThreads, "poll fail during SHUT_RDWR")
    sock.close()

  def PollWhenReceiveFinTest(self, version):
    netid = self.RandomNetid()
    expected = select.POLLIN
    sock, multiThreads = self.PollRepairSocketInMultipleThreads(netid, version, expected)
    self.receiveFin(netid, version, sock)
    self.assertThreadsStopped(multiThreads, "poll fail during FIN")
    sock.close()

  # Test whether socket idle can be detected by SIOCINQ and SIOCOUTQ.
  def testSocketIdle(self):
    for version in [4, 5, 6]:
      self.readQueueIdleTest(version)
      self.writeQueueIdleTest(version)

  def readQueueIdleTest(self, version):
    netid = self.RandomNetid()
    sock = self.createConnectedSocket(version, netid)

    buf = ctypes.c_int()
    fcntl.ioctl(sock, SIOCINQ, buf)
    self.assertEquals(buf.value, 0)

    TEST_RECV_PAYLOAD = net_test.UDP_PAYLOAD
    self.receiveData(netid, version, TEST_RECV_PAYLOAD)
    fcntl.ioctl(sock, SIOCINQ, buf)
    self.assertEquals(buf.value, len(TEST_RECV_PAYLOAD))
    sock.close()

  def writeQueueIdleTest(self, version):
    netid = self.RandomNetid()
    # Setup a connected socket, write queue is empty.
    sock = self.createConnectedSocket(version, netid)
    buf = ctypes.c_int()
    fcntl.ioctl(sock, SIOCOUTQ, buf)
    self.assertEquals(buf.value, 0)
    # Change to repair mode with SEND_QUEUE, writing some data to the queue.
    sock.setsockopt(SOL_TCP, TCP_REPAIR, TCP_REPAIR_ON)
    TEST_SEND_PAYLOAD = net_test.UDP_PAYLOAD
    sock.setsockopt(SOL_TCP, TCP_REPAIR_QUEUE, TCP_SEND_QUEUE)
    self.sendData(netid, version, sock, TEST_SEND_PAYLOAD)
    fcntl.ioctl(sock, SIOCOUTQ, buf)
    self.assertEquals(buf.value, len(TEST_SEND_PAYLOAD))
    sock.close()

    # Setup a connected socket again.
    netid = self.RandomNetid()
    sock = self.createConnectedSocket(version, netid)
    # Send out some data and don't receive ACK yet.
    self.sendData(netid, version, sock, TEST_SEND_PAYLOAD)
    fcntl.ioctl(sock, SIOCOUTQ, buf)
    self.assertEquals(buf.value, len(TEST_SEND_PAYLOAD))
    # Receive response ACK.
    remoteaddr = self.GetRemoteAddress(version)
    myaddr = self.MyAddress(version, netid)
    desc_ack, ack = packets.ACK(version, remoteaddr, myaddr, self.last_sent)
    self.ReceivePacketOn(netid, ack)
    fcntl.ioctl(sock, SIOCOUTQ, buf)
    self.assertEquals(buf.value, 0)
    sock.close()


  def fdSelect(self, sock, expected):
    READ_ONLY = select.POLLIN | select.POLLPRI | select.POLLHUP | select.POLLERR | select.POLLNVAL
    p = select.poll()
    p.register(sock, READ_ONLY)
    events = p.poll(500)
    for fd,event in events:
      if fd == sock.fileno():
        self.assertEquals(event, expected)
      else:
        raise AssertionError("unexpected poll fd")

class SocketExceptionThread(threading.Thread):

  def __init__(self, sock, operation):
    self.exception = None
    super(SocketExceptionThread, self).__init__()
    self.daemon = True
    self.sock = sock
    self.operation = operation

  def stop(self):
    self._Thread__stop()

  def run(self):
    try:
      self.operation(self.sock)
    except (IOError, AssertionError), e:
      self.exception = e

if __name__ == '__main__':
  unittest.main()
