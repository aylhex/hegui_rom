#!/usr/bin/python
#
# Copyright 2016 The Android Open Source Project
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

from errno import *  # pylint: disable=wildcard-import
from socket import *  # pylint: disable=wildcard-import
import threading
import time
import unittest

import csocket
import net_test


class LeakTest(net_test.NetworkTest):

  def testRecvfromLeak(self):
    s = socket(AF_INET6, SOCK_DGRAM, 0)
    s.bind(("::1", 0))

    # Call shutdown on another thread while a recvfrom is in progress.
    csocket.SetSocketTimeout(s, 2000)
    def ShutdownSocket():
      time.sleep(0.5)
      self.assertRaisesErrno(ENOTCONN, s.shutdown, SHUT_RDWR)

    t = threading.Thread(target=ShutdownSocket)
    t.start()

    # This could have been written with just "s.recvfrom", but because we're
    # testing for a bug where the kernel returns garbage, it's probably safer
    # to call the syscall directly.
    data, addr = csocket.Recvfrom(s, 4096)
    self.assertEqual("", data)
    self.assertEqual(None, addr)


class ForceSocketBufferOptionTest(net_test.NetworkTest):

  SO_SNDBUFFORCE = 32
  SO_RCVBUFFORCE = 33

  def CheckForceSocketBufferOption(self, option, force_option):
    s = socket(AF_INET6, SOCK_DGRAM, 0)

    # Find the minimum buffer value.
    s.setsockopt(SOL_SOCKET, option, 0)
    minbuf = s.getsockopt(SOL_SOCKET, option)

    # Check that the force option works to set reasonable values.
    val = 4097
    self.assertGreater(2 * val, minbuf)
    s.setsockopt(SOL_SOCKET, force_option, val)
    self.assertEquals(2 * val, s.getsockopt(SOL_SOCKET, option))

    # Check that the force option sets the minimum value instead of a negative
    # value on integer overflow. Because the kernel multiplies passed-in values
    # by 2, pick a value that becomes a small negative number if treated as
    # unsigned.
    bogusval = 2 ** 31 - val
    s.setsockopt(SOL_SOCKET, force_option, bogusval)
    self.assertEquals(minbuf, s.getsockopt(SOL_SOCKET, option))

  def testRcvBufForce(self):
    self.CheckForceSocketBufferOption(SO_RCVBUF, self.SO_RCVBUFFORCE)

  def testRcvBufForce(self):
    self.CheckForceSocketBufferOption(SO_SNDBUF, self.SO_SNDBUFFORCE)


if __name__ == "__main__":
  unittest.main()
