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

import errno
import random
from socket import *  # pylint: disable=wildcard-import
import time
import unittest

from scapy import all as scapy

import csocket
import iproute
import multinetwork_base
import packets
import net_test

# Setsockopt values.
IPV6_ADDR_PREFERENCES = 72
IPV6_PREFER_SRC_PUBLIC = 0x0002

# The retrans timer is also the DAD timeout. We set this to a value that's not
# so short that DAD will complete before we attempt to use the network, but
# short enough that we don't have to wait too long for DAD to complete.
RETRANS_TIMER = 150


class IPv6SourceAddressSelectionTest(multinetwork_base.MultiNetworkBaseTest):
  """Test for IPv6 source address selection.

  Relevant kernel commits:
    upstream net-next:
      7fd2561 net: ipv6: Add a sysctl to make optimistic addresses useful candidates
      c58da4c net: ipv6: allow explicitly choosing optimistic addresses
      9131f3d ipv6: Do not iterate over all interfaces when finding source address on specific interface.
      c0b8da1 ipv6: Fix finding best source address in ipv6_dev_get_saddr().
      c15df30 ipv6: Remove unused arguments for __ipv6_dev_get_saddr().
      3985e8a ipv6: sysctl to restrict candidate source addresses

    android-3.10:
      2ce95507 net: ipv6: Add a sysctl to make optimistic addresses useful candidates
      0065bf4 net: ipv6: allow choosing optimistic addresses with use_optimistic
      0633924 ipv6: sysctl to restrict candidate source addresses
  """

  def SetIPv6Sysctl(self, ifname, sysctl, value):
    self.SetSysctl("/proc/sys/net/ipv6/conf/%s/%s" % (ifname, sysctl), value)

  def SetDAD(self, ifname, value):
    self.SetSysctl("/proc/sys/net/ipv6/conf/%s/accept_dad" % ifname, value)
    self.SetSysctl("/proc/sys/net/ipv6/conf/%s/dad_transmits" % ifname, value)

  def SetOptimisticDAD(self, ifname, value):
    self.SetSysctl("/proc/sys/net/ipv6/conf/%s/optimistic_dad" % ifname, value)

  def SetUseTempaddrs(self, ifname, value):
    self.SetSysctl("/proc/sys/net/ipv6/conf/%s/use_tempaddr" % ifname, value)

  def SetUseOptimistic(self, ifname, value):
    self.SetSysctl("/proc/sys/net/ipv6/conf/%s/use_optimistic" % ifname, value)

  def GetSourceIP(self, netid, mode="mark"):
    s = self.BuildSocket(6, net_test.UDPSocket, netid, mode)
    # Because why not...testing for temporary addresses is a separate thing.
    s.setsockopt(IPPROTO_IPV6, IPV6_ADDR_PREFERENCES, IPV6_PREFER_SRC_PUBLIC)

    s.connect((net_test.IPV6_ADDR, 123))
    src_addr = s.getsockname()[0]
    self.assertTrue(src_addr)
    return src_addr

  def assertAddressNotPresent(self, address):
    self.assertRaises(IOError, self.iproute.GetAddress, address)

  def assertAddressHasExpectedAttributes(
      self, address, expected_ifindex, expected_flags):
    ifa_msg = self.iproute.GetAddress(address)[0]
    self.assertEquals(AF_INET6 if ":" in address else AF_INET, ifa_msg.family)
    self.assertEquals(64, ifa_msg.prefixlen)
    self.assertEquals(iproute.RT_SCOPE_UNIVERSE, ifa_msg.scope)
    self.assertEquals(expected_ifindex, ifa_msg.index)
    self.assertEquals(expected_flags, ifa_msg.flags & expected_flags)

  def AddressIsTentative(self, address):
    ifa_msg = self.iproute.GetAddress(address)[0]
    return ifa_msg.flags & iproute.IFA_F_TENTATIVE

  def BindToAddress(self, address):
    s = net_test.UDPSocket(AF_INET6)
    s.bind((address, 0, 0, 0))

  def SendWithSourceAddress(self, address, netid, dest=net_test.IPV6_ADDR):
    pktinfo = multinetwork_base.MakePktInfo(6, address, 0)
    cmsgs = [(net_test.SOL_IPV6, IPV6_PKTINFO, pktinfo)]
    s = self.BuildSocket(6, net_test.UDPSocket, netid, "mark")
    return csocket.Sendmsg(s, (dest, 53), "Hello", cmsgs, 0)

  def assertAddressUsable(self, address, netid):
    self.BindToAddress(address)
    self.SendWithSourceAddress(address, netid)
    # No exceptions? Good.

  def assertAddressNotUsable(self, address, netid):
    self.assertRaisesErrno(errno.EADDRNOTAVAIL, self.BindToAddress, address)
    self.assertRaisesErrno(errno.EINVAL,
                           self.SendWithSourceAddress, address, netid)

  def assertAddressSelected(self, address, netid):
    self.assertEquals(address, self.GetSourceIP(netid))

  def assertAddressNotSelected(self, address, netid):
    self.assertNotEquals(address, self.GetSourceIP(netid))

  def WaitForDad(self, address):
    for _ in xrange(20):
      if not self.AddressIsTentative(address):
        return
      time.sleep(0.1)
    raise AssertionError("%s did not complete DAD after 2 seconds")


class MultiInterfaceSourceAddressSelectionTest(IPv6SourceAddressSelectionTest):

  def setUp(self):
    # [0]  Make sure DAD, optimistic DAD, and the use_optimistic option
    # are all consistently disabled at the outset.
    for netid in self.tuns:
      ifname = self.GetInterfaceName(netid)
      self.SetDAD(ifname, 0)
      self.SetOptimisticDAD(ifname, 0)
      self.SetUseTempaddrs(ifname, 0)
      self.SetUseOptimistic(ifname, 0)
      self.SetIPv6Sysctl(ifname, "use_oif_addrs_only", 0)

    # [1]  Pick an interface on which to test.
    self.test_netid = random.choice(self.tuns.keys())
    self.test_ip = self.MyAddress(6, self.test_netid)
    self.test_ifindex = self.ifindices[self.test_netid]
    self.test_ifname = self.GetInterfaceName(self.test_netid)
    self.test_lladdr = net_test.GetLinkAddress(self.test_ifname, True)

    # [2]  Delete the test interface's IPv6 address.
    self.iproute.DelAddress(self.test_ip, 64, self.test_ifindex)
    self.assertAddressNotPresent(self.test_ip)

    self.assertAddressNotUsable(self.test_ip, self.test_netid)
    # Verify that the link-local address is not tentative.
    # Even though we disable DAD above, without this change occasionally the
    # test fails. This might be due to us disabling DAD only after the
    # link-local address is generated.
    self.WaitForDad(self.test_lladdr)


class TentativeAddressTest(MultiInterfaceSourceAddressSelectionTest):

  def testRfc6724Behaviour(self):
    # [3]  Get an IPv6 address back, in DAD start-up.
    self.SetDAD(self.test_ifname, 1)  # Enable DAD
    # Send a RA to start SLAAC and subsequent DAD.
    self.SendRA(self.test_netid, retranstimer=RETRANS_TIMER)
    # Get flags and prove tentative-ness.
    self.assertAddressHasExpectedAttributes(
        self.test_ip, self.test_ifindex, iproute.IFA_F_TENTATIVE)

    # Even though the interface has an IPv6 address, its tentative nature
    # prevents it from being selected.
    self.assertAddressNotUsable(self.test_ip, self.test_netid)
    self.assertAddressNotSelected(self.test_ip, self.test_netid)

    # Busy wait for DAD to complete (should be less than 1 second).
    self.WaitForDad(self.test_ip)

    # The test_ip should have completed DAD by now, and should be the
    # chosen source address, eligible to bind to, etc.
    self.assertAddressUsable(self.test_ip, self.test_netid)
    self.assertAddressSelected(self.test_ip, self.test_netid)


class OptimisticAddressTest(MultiInterfaceSourceAddressSelectionTest):

  def testRfc6724Behaviour(self):
    # [3]  Get an IPv6 address back, in optimistic DAD start-up.
    self.SetDAD(self.test_ifname, 1)  # Enable DAD
    self.SetOptimisticDAD(self.test_ifname, 1)
    # Send a RA to start SLAAC and subsequent DAD.
    self.SendRA(self.test_netid, retranstimer=RETRANS_TIMER)
    # Get flags and prove optimism.
    self.assertAddressHasExpectedAttributes(
        self.test_ip, self.test_ifindex, iproute.IFA_F_OPTIMISTIC)

    # Optimistic addresses are usable but are not selected.
    if net_test.LINUX_VERSION >= (3, 18, 0):
      # The version checked in to android kernels <= 3.10 requires the
      # use_optimistic sysctl to be turned on.
      self.assertAddressUsable(self.test_ip, self.test_netid)
    self.assertAddressNotSelected(self.test_ip, self.test_netid)

    # Busy wait for DAD to complete (should be less than 1 second).
    self.WaitForDad(self.test_ip)

    # The test_ip should have completed DAD by now, and should be the
    # chosen source address.
    self.assertAddressUsable(self.test_ip, self.test_netid)
    self.assertAddressSelected(self.test_ip, self.test_netid)


class OptimisticAddressOkayTest(MultiInterfaceSourceAddressSelectionTest):

  def testModifiedRfc6724Behaviour(self):
    # [3]  Get an IPv6 address back, in optimistic DAD start-up.
    self.SetDAD(self.test_ifname, 1)  # Enable DAD
    self.SetOptimisticDAD(self.test_ifname, 1)
    self.SetUseOptimistic(self.test_ifname, 1)
    # Send a RA to start SLAAC and subsequent DAD.
    self.SendRA(self.test_netid, retranstimer=RETRANS_TIMER)
    # Get flags and prove optimistism.
    self.assertAddressHasExpectedAttributes(
        self.test_ip, self.test_ifindex, iproute.IFA_F_OPTIMISTIC)

    # The interface has an IPv6 address and, despite its optimistic nature,
    # the use_optimistic option allows it to be selected.
    self.assertAddressUsable(self.test_ip, self.test_netid)
    self.assertAddressSelected(self.test_ip, self.test_netid)


class ValidBeforeOptimisticTest(MultiInterfaceSourceAddressSelectionTest):

  def testModifiedRfc6724Behaviour(self):
    # [3]  Add a valid IPv6 address to this interface and verify it is
    # selected as the source address.
    preferred_ip = self.OnlinkPrefix(6, self.test_netid) + "cafe"
    self.iproute.AddAddress(preferred_ip, 64, self.test_ifindex)
    self.assertAddressHasExpectedAttributes(
        preferred_ip, self.test_ifindex, iproute.IFA_F_PERMANENT)
    self.assertEquals(preferred_ip, self.GetSourceIP(self.test_netid))

    # [4]  Get another IPv6 address, in optimistic DAD start-up.
    self.SetDAD(self.test_ifname, 1)  # Enable DAD
    self.SetOptimisticDAD(self.test_ifname, 1)
    self.SetUseOptimistic(self.test_ifname, 1)
    # Send a RA to start SLAAC and subsequent DAD.
    self.SendRA(self.test_netid, retranstimer=RETRANS_TIMER)
    # Get flags and prove optimism.
    self.assertAddressHasExpectedAttributes(
        self.test_ip, self.test_ifindex, iproute.IFA_F_OPTIMISTIC)

    # Since the interface has another IPv6 address, the optimistic address
    # is not selected--the other, valid address is chosen.
    self.assertAddressUsable(self.test_ip, self.test_netid)
    self.assertAddressNotSelected(self.test_ip, self.test_netid)
    self.assertAddressSelected(preferred_ip, self.test_netid)


class DadFailureTest(MultiInterfaceSourceAddressSelectionTest):

  def testDadFailure(self):
    # [3]  Get an IPv6 address back, in optimistic DAD start-up.
    self.SetDAD(self.test_ifname, 1)  # Enable DAD
    self.SetOptimisticDAD(self.test_ifname, 1)
    self.SetUseOptimistic(self.test_ifname, 1)
    # Send a RA to start SLAAC and subsequent DAD.
    self.SendRA(self.test_netid, retranstimer=RETRANS_TIMER)
    # Prove optimism and usability.
    self.assertAddressHasExpectedAttributes(
        self.test_ip, self.test_ifindex, iproute.IFA_F_OPTIMISTIC)
    self.assertAddressUsable(self.test_ip, self.test_netid)
    self.assertAddressSelected(self.test_ip, self.test_netid)

    # Send a NA for the optimistic address, indicating address conflict
    # ("DAD defense").
    conflict_macaddr = "02:00:0b:ad:d0:0d"
    dad_defense = (scapy.Ether(src=conflict_macaddr, dst="33:33:33:00:00:01") /
                   scapy.IPv6(src=self.test_ip, dst="ff02::1") /
                   scapy.ICMPv6ND_NA(tgt=self.test_ip, R=0, S=0, O=1) /
                   scapy.ICMPv6NDOptDstLLAddr(lladdr=conflict_macaddr))
    self.ReceiveEtherPacketOn(self.test_netid, dad_defense)

    # The address should have failed DAD, and therefore no longer be usable.
    self.assertAddressNotUsable(self.test_ip, self.test_netid)
    self.assertAddressNotSelected(self.test_ip, self.test_netid)

    # TODO(ek): verify that an RTM_DELADDR issued for the DAD-failed address.


class NoNsFromOptimisticTest(MultiInterfaceSourceAddressSelectionTest):

  def testSendToOnlinkDestination(self):
    # [3]  Get an IPv6 address back, in optimistic DAD start-up.
    self.SetDAD(self.test_ifname, 1)  # Enable DAD
    self.SetOptimisticDAD(self.test_ifname, 1)
    self.SetUseOptimistic(self.test_ifname, 1)
    # Send a RA to start SLAAC and subsequent DAD.
    self.SendRA(self.test_netid, retranstimer=RETRANS_TIMER)
    # Prove optimism and usability.
    self.assertAddressHasExpectedAttributes(
        self.test_ip, self.test_ifindex, iproute.IFA_F_OPTIMISTIC)
    self.assertAddressUsable(self.test_ip, self.test_netid)
    self.assertAddressSelected(self.test_ip, self.test_netid)

    # [4]  Send to an on-link destination and observe a Neighbor Solicitation
    # packet with a source address that is NOT the optimistic address.
    # In this setup, the only usable address is the link-local address.
    onlink_dest = self.GetRandomDestination(
        self.OnlinkPrefix(6, self.test_netid))
    self.SendWithSourceAddress(self.test_ip, self.test_netid, onlink_dest)

    if net_test.LINUX_VERSION >= (3, 18, 0):
      # Older versions will actually choose the optimistic address to
      # originate Neighbor Solications (RFC violation).
      expected_ns = packets.NS(
          self.test_lladdr,
          onlink_dest,
          self.MyMacAddress(self.test_netid))[1]
      self.ExpectPacketOn(self.test_netid, "link-local NS", expected_ns)


# TODO(ek): add tests listening for netlink events.


class DefaultCandidateSrcAddrsTest(MultiInterfaceSourceAddressSelectionTest):

  def testChoosesNonInterfaceSourceAddress(self):
    self.SetIPv6Sysctl(self.test_ifname, "use_oif_addrs_only", 0)
    src_ip = self.GetSourceIP(self.test_netid)
    self.assertFalse(src_ip in [self.test_ip, self.test_lladdr])
    self.assertTrue(src_ip in
                    [self.MyAddress(6, netid)
                     for netid in self.tuns if netid != self.test_netid])


class RestrictedCandidateSrcAddrsTest(MultiInterfaceSourceAddressSelectionTest):

  def testChoosesOnlyInterfaceSourceAddress(self):
    self.SetIPv6Sysctl(self.test_ifname, "use_oif_addrs_only", 1)
    # self.test_ifname does not have a global IPv6 address, so the only
    # candidate is the existing link-local address.
    self.assertAddressSelected(self.test_lladdr, self.test_netid)


if __name__ == "__main__":
  unittest.main()
