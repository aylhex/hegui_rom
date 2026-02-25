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

# ----------------------------------------------------------------------

# This triggers a kernel panic on 4.9.114+ which is fixed in 4.9.136
#
# Crash was introduced by ad8b1ffc3efae2f65080bdb11145c87d299b8f9a
# and reverted in 2edec22d18758c9b29301ded2291f051d65422e9

# ----------------------------------------------------------------------

# Modules linked in:
# Pid: 305, comm: python Not tainted 4.9.114
# RIP: 0033:[<0000000060272d73>]
# RSP: 000000007fd09a10  EFLAGS: 00010246
# RAX: 0000000060492fa8 RBX: 0000000060272b18 RCX: 000000007ff412a8
# RDX: 000000007ff41288 RSI: 000000007fd09a98 RDI: 000000007ff14a00
# RBP: 000000007fd09a40 R08: 0000000000000001 R09: 0100000000000000
# R10: 0000000000000000 R11: 000000007ff412a8 R12: 0000000000010002
# R13: 000000000000000a R14: 0000000000000000 R15: 0000000000000000
# Kernel panic - not syncing: Kernel mode fault at addr 0x48, ip 0x60272d73
# CPU: 0 PID: 305 Comm: python Not tainted 4.9.114 #7
# Stack:
#  7fcd5000 7ff411e0 7ff14a00 7ff41000
#  00000000 00000000 7fd09b00 6031acd9
#  00000000 7ff41288 7ff4100c 100000003
# Call Trace:
#  [<6031acd9>] ip6t_do_table+0x2a3/0x3d4
#  [<6026d300>] ? netfilter_net_init+0xd5/0x14f
#  [<6026d37a>] ? nf_iterate+0x0/0x5c
#  [<6031c99d>] ip6table_filter_hook+0x21/0x23
#  [<6026d3b2>] nf_iterate+0x38/0x5c
#  [<6026d40a>] nf_hook_slow+0x34/0xa2
#  [<6003166c>] ? set_signals+0x0/0x3f
#  [<6003165d>] ? get_signals+0x0/0xf
#  [<603045d4>] rawv6_sendmsg+0x842/0xc4b
#  [<60033d15>] ? wait_stub_done+0x40/0x10a
#  [<60021176>] ? copy_chunk_from_user+0x23/0x2e
#  [<60021153>] ? copy_chunk_from_user+0x0/0x2e
#  [<60302da3>] ? dst_output+0x0/0x11
#  [<602b063a>] inet_sendmsg+0x1e/0x5c
#  [<600fe142>] ? __fdget+0x15/0x17
#  [<6022636c>] sock_sendmsg+0xf/0x62
#  [<6022785d>] SyS_sendto+0x108/0x140
#  [<600389c2>] ? arch_switch_to+0x2b/0x2e
#  [<60367ce4>] ? __schedule+0x428/0x44f
#  [<603678bc>] ? __schedule+0x0/0x44f
#  [<60021125>] handle_syscall+0x79/0xa7
#  [<6003445c>] userspace+0x3bb/0x453
#  [<6001dd92>] ? interrupt_end+0x0/0x94
#  [<6001dc42>] fork_handler+0x85/0x87
#
# /android/kernel/tests/net/test/run_net_test.sh: line 397: 50828 Aborted
# $KERNEL_BINARY umid=net_test mem=512M $blockdevice=$SCRIPT_DIR/$ROOTFS $netconfig $consolemode $cmdline 1>&2
# Returning exit code 134.

# ----------------------------------------------------------------------

import os
import socket
import unittest

import net_test

class RemovedFeatureTest(net_test.NetworkTest):

  def setUp(self):
    net_test.RunIptablesCommand(6, "-I OUTPUT 1 -m policy --dir out --pol ipsec")

  def tearDown(self):
    net_test.RunIptablesCommand(6, "-D OUTPUT -m policy --dir out --pol ipsec")

  def testPolicyNetfilterFragPanic(self):
    ipv6_min_mtu = 1280
    ipv6_header_size = 40
    ipv6_frag_header_size = 8

    pkt1_frag_len = ipv6_min_mtu - ipv6_header_size - ipv6_frag_header_size
    pkt2_frag_len = 1

    ip6loopback = '00000000000000000000000000000001'   # ::1

    # 40 byte IPv6 header
    ver6 = '6'
    tclass = '00'
    flowlbl = '00000'
    # (uint16) payload length - of rest of packets in octets
    pkt1_plen = '%04x' % (ipv6_frag_header_size + pkt1_frag_len)
    pkt2_plen = '%04x' % (ipv6_frag_header_size + pkt2_frag_len)
    nexthdr = '2c'   # = 44 IPv6-Frag
    hoplimit = '00'
    src = ip6loopback
    dst = ip6loopback

    # 8 byte IPv6 fragmentation header
    frag_nexthdr = '00'
    frag_reserved = '00'
    # 13-bit offset, 2-bit reserved, 1-bit M[ore] flag
    pkt1_frag_offset = '0001'
    pkt2_frag_offset = '%04x' % pkt1_frag_len
    frag_identification = '00000000'

    # Fragmentation payload
    pkt1_frag_payload = '00' * pkt1_frag_len
    pkt2_frag_payload = '00' * pkt2_frag_len

    pkt1 = (ver6 + tclass + flowlbl + pkt1_plen + nexthdr + hoplimit + src + dst
         + frag_nexthdr + frag_reserved + pkt1_frag_offset + frag_identification
         + pkt1_frag_payload)
    pkt2 = (ver6 + tclass + flowlbl + pkt2_plen + nexthdr + hoplimit + src + dst
         + frag_nexthdr + frag_reserved + pkt2_frag_offset + frag_identification
         + pkt2_frag_payload)

    s = socket.socket(socket.AF_INET6, socket.SOCK_RAW, socket.IPPROTO_RAW)
    s.sendto(pkt1.decode('hex'), ('::1', 0))
    s.sendto(pkt2.decode('hex'), ('::1', 0))
    s.close()


if __name__ == "__main__":
  unittest.main()
