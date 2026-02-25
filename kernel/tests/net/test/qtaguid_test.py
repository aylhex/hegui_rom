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

"""Unit tests for xt_qtaguid."""

import errno
from socket import *  # pylint: disable=wildcard-import
import unittest
import os

import net_test
import packets
import tcp_test

CTRL_PROCPATH = "/proc/net/xt_qtaguid/ctrl"
OTHER_UID_GID = 12345
HAVE_QTAGUID = os.path.exists(CTRL_PROCPATH)


@unittest.skipUnless(HAVE_QTAGUID, "xt_qtaguid not supported")
class QtaguidTest(tcp_test.TcpBaseTest):

  def RunIptablesCommand(self, args):
    self.assertFalse(net_test.RunIptablesCommand(4, args))
    self.assertFalse(net_test.RunIptablesCommand(6, args))

  def setUp(self):
    self.RunIptablesCommand("-N qtaguid_test_OUTPUT")
    self.RunIptablesCommand("-A OUTPUT -j qtaguid_test_OUTPUT")

  def tearDown(self):
    self.RunIptablesCommand("-D OUTPUT -j qtaguid_test_OUTPUT")
    self.RunIptablesCommand("-F qtaguid_test_OUTPUT")
    self.RunIptablesCommand("-X qtaguid_test_OUTPUT")

  def WriteToCtrl(self, command):
    ctrl_file = open(CTRL_PROCPATH, 'w')
    ctrl_file.write(command)
    ctrl_file.close()

  def CheckTag(self, tag, uid):
    for line in open(CTRL_PROCPATH, 'r').readlines():
      if "tag=0x%x (uid=%d)" % ((tag|uid), uid) in line:
        return True
    return False

  def SetIptablesRule(self, version, is_add, is_gid, my_id, inverted):
    add_del = "-A" if is_add else "-D"
    uid_gid = "--gid-owner" if is_gid else "--uid-owner"
    if inverted:
      args = "%s qtaguid_test_OUTPUT -m owner ! %s %d -j DROP" % (add_del, uid_gid, my_id)
    else:
      args = "%s qtaguid_test_OUTPUT -m owner %s %d -j DROP" % (add_del, uid_gid, my_id)
    self.assertFalse(net_test.RunIptablesCommand(version, args))

  def AddIptablesRule(self, version, is_gid, myId):
    self.SetIptablesRule(version, True, is_gid, myId, False)

  def AddIptablesInvertedRule(self, version, is_gid, myId):
    self.SetIptablesRule(version, True, is_gid, myId, True)

  def DelIptablesRule(self, version, is_gid, myId):
    self.SetIptablesRule(version, False, is_gid, myId, False)

  def DelIptablesInvertedRule(self, version, is_gid, myId):
    self.SetIptablesRule(version, False, is_gid, myId, True)

  def CheckSocketOutput(self, version, is_gid):
    myId = os.getgid() if is_gid else os.getuid()
    self.AddIptablesRule(version, is_gid, myId)
    family = {4: AF_INET, 6: AF_INET6}[version]
    s = socket(family, SOCK_DGRAM, 0)
    addr = {4: "127.0.0.1", 6: "::1"}[version]
    s.bind((addr, 0))
    addr = s.getsockname()
    self.assertRaisesErrno(errno.EPERM, s.sendto, "foo", addr)
    self.DelIptablesRule(version, is_gid, myId)
    s.sendto("foo", addr)
    data, sockaddr = s.recvfrom(4096)
    self.assertEqual("foo", data)
    self.assertEqual(sockaddr, addr)

  def CheckSocketOutputInverted(self, version, is_gid):
    # Load a inverted iptable rule on current uid/gid 0, traffic from other
    # uid/gid should be blocked and traffic from current uid/gid should pass.
    myId = os.getgid() if is_gid else os.getuid()
    self.AddIptablesInvertedRule(version, is_gid, myId)
    family = {4: AF_INET, 6: AF_INET6}[version]
    s = socket(family, SOCK_DGRAM, 0)
    addr1 = {4: "127.0.0.1", 6: "::1"}[version]
    s.bind((addr1, 0))
    addr1 = s.getsockname()
    s.sendto("foo", addr1)
    data, sockaddr = s.recvfrom(4096)
    self.assertEqual("foo", data)
    self.assertEqual(sockaddr, addr1)
    with net_test.RunAsUidGid(0 if is_gid else 12345,
                              12345 if is_gid else 0):
      s2 = socket(family, SOCK_DGRAM, 0)
      addr2 = {4: "127.0.0.1", 6: "::1"}[version]
      s2.bind((addr2, 0))
      addr2 = s2.getsockname()
      self.assertRaisesErrno(errno.EPERM, s2.sendto, "foo", addr2)
    self.DelIptablesInvertedRule(version, is_gid, myId)
    s.sendto("foo", addr1)
    data, sockaddr = s.recvfrom(4096)
    self.assertEqual("foo", data)
    self.assertEqual(sockaddr, addr1)

  def SendRSTOnClosedSocket(self, version, netid, expect_rst):
    self.IncomingConnection(version, tcp_test.TCP_ESTABLISHED, netid)
    self.accepted.setsockopt(net_test.SOL_TCP, net_test.TCP_LINGER2, -1)
    net_test.EnableFinWait(self.accepted)
    self.accepted.shutdown(SHUT_WR)
    desc, fin = self.FinPacket()
    self.ExpectPacketOn(netid, "Closing FIN_WAIT1 socket", fin)
    finversion = 4 if version == 5 else version
    desc, finack = packets.ACK(finversion, self.remoteaddr, self.myaddr, fin)
    self.ReceivePacketOn(netid, finack)
    try:
      self.ExpectPacketOn(netid, "Closing FIN_WAIT1 socket", fin)
    except AssertionError:
      pass
    self.accepted.close()
    desc, rst = packets.RST(version, self.myaddr, self.remoteaddr, self.last_packet)
    if expect_rst:
      msg = "closing socket with linger2, expecting %s: " % desc
      self.ExpectPacketOn(netid, msg, rst)
    else:
      msg = "closing socket with linger2, expecting no packets"
      self.ExpectNoPacketsOn(netid, msg)

  def CheckUidGidCombination(self, version, invert_gid, invert_uid):
    my_uid = os.getuid()
    my_gid = os.getgid()
    if invert_gid:
      self.AddIptablesInvertedRule(version, True, my_gid)
    else:
      self.AddIptablesRule(version, True, OTHER_UID_GID)
    if invert_uid:
      self.AddIptablesInvertedRule(version, False, my_uid)
    else:
      self.AddIptablesRule(version, False, OTHER_UID_GID)
    for netid in self.NETIDS:
      self.SendRSTOnClosedSocket(version, netid, not invert_gid)
    if invert_gid:
      self.DelIptablesInvertedRule(version, True, my_gid)
    else:
      self.DelIptablesRule(version, True, OTHER_UID_GID)
    if invert_uid:
      self.AddIptablesInvertedRule(version, False, my_uid)
    else:
      self.DelIptablesRule(version, False, OTHER_UID_GID)

  def testCloseWithoutUntag(self):
    self.dev_file = open("/dev/xt_qtaguid", "r");
    sk = socket(AF_INET, SOCK_DGRAM, 0)
    uid = os.getuid()
    tag = 0xff00ff00 << 32
    command =  "t %d %d %d" % (sk.fileno(), tag, uid)
    self.WriteToCtrl(command)
    self.assertTrue(self.CheckTag(tag, uid))
    sk.close();
    self.assertFalse(self.CheckTag(tag, uid))
    self.dev_file.close();

  def testTagWithoutDeviceOpen(self):
    sk = socket(AF_INET, SOCK_DGRAM, 0)
    uid = os.getuid()
    tag = 0xff00ff00 << 32
    command = "t %d %d %d" % (sk.fileno(), tag, uid)
    self.WriteToCtrl(command)
    self.assertTrue(self.CheckTag(tag, uid))
    self.dev_file = open("/dev/xt_qtaguid", "r")
    sk.close()
    self.assertFalse(self.CheckTag(tag, uid))
    self.dev_file.close();

  def testUidGidMatch(self):
    self.CheckSocketOutput(4, False)
    self.CheckSocketOutput(6, False)
    self.CheckSocketOutput(4, True)
    self.CheckSocketOutput(6, True)
    self.CheckSocketOutputInverted(4, True)
    self.CheckSocketOutputInverted(6, True)
    self.CheckSocketOutputInverted(4, False)
    self.CheckSocketOutputInverted(6, False)

  def testCheckNotMatchGid(self):
    self.assertIn("match_no_sk_gid", open(CTRL_PROCPATH, 'r').read())

  def testRstPacketNotDropped(self):
    my_uid = os.getuid()
    self.AddIptablesInvertedRule(4, False, my_uid)
    for netid in self.NETIDS:
      self.SendRSTOnClosedSocket(4, netid, True)
    self.DelIptablesInvertedRule(4, False, my_uid)
    self.AddIptablesInvertedRule(6, False, my_uid)
    for netid in self.NETIDS:
      self.SendRSTOnClosedSocket(6, netid, True)
    self.DelIptablesInvertedRule(6, False, my_uid)

  def testUidGidCombineMatch(self):
    self.CheckUidGidCombination(4, invert_gid=True, invert_uid=True)
    self.CheckUidGidCombination(4, invert_gid=True, invert_uid=False)
    self.CheckUidGidCombination(4, invert_gid=False, invert_uid=True)
    self.CheckUidGidCombination(4, invert_gid=False, invert_uid=False)
    self.CheckUidGidCombination(6, invert_gid=True, invert_uid=True)
    self.CheckUidGidCombination(6, invert_gid=True, invert_uid=False)
    self.CheckUidGidCombination(6, invert_gid=False, invert_uid=True)
    self.CheckUidGidCombination(6, invert_gid=False, invert_uid=False)


if __name__ == "__main__":
  unittest.main()
