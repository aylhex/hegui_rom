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
"""A utility for "twisting" packets on a tun/tap interface.

TunTwister and TapTwister echo packets on a tun/tap while swapping the source
and destination at the ethernet and IP layers. This allows sockets to
effectively loop back packets through the full networking stack, avoiding any
shortcuts the kernel may take for actual IP loopback. Additionally, users can
inspect each packet to assert testing invariants.
"""

import os
import select
import threading
from scapy import all as scapy


class TunTwister(object):
  """TunTwister transports traffic travelling twixt two terminals.

  TunTwister is a context manager that will read packets from a tun file
  descriptor, swap the source and dest of the IP header, and write them back.
  To use this class, tests also need to set up routing so that packets will be
  routed to the tun interface.

  Two sockets can communicate with each other through a TunTwister as if they
  were each connecting to a remote endpoint. Both sockets will have the
  perspective that the address of the other is a remote address.

  Packet inspection can be done with a validator function. This can be any
  function that takes a scapy packet object as its only argument. Exceptions
  raised by your validator function will be re-raised on the main thread to fail
  your tests.

  NOTE: Exceptions raised by a validator function will supercede exceptions
  raised in the context.

  EXAMPLE:
    def testFeatureFoo(self):
      my_tun = MakeTunInterface()
      # Set up routing so packets go to my_tun.

      def ValidatePortNumber(packet):
        self.assertEquals(8080, packet.getlayer(scapy.UDP).sport)
        self.assertEquals(8080, packet.getlayer(scapy.UDP).dport)

      with TunTwister(tun_fd=my_tun, validator=ValidatePortNumber):
        sock = socket(AF_INET, SOCK_DGRAM, 0)
        sock.bind(("0.0.0.0", 8080))
        sock.settimeout(1.0)
        sock.sendto("hello", ("1.2.3.4", 8080))
        data, addr = sock.recvfrom(1024)
        self.assertEquals("hello", data)
        self.assertEquals(("1.2.3.4", 8080), addr)
  """

  # Hopefully larger than any packet.
  _READ_BUF_SIZE = 2048
  _POLL_TIMEOUT_SEC = 2.0
  _POLL_FAST_TIMEOUT_MS = 100

  def __init__(self, fd=None, validator=None):
    """Construct a TunTwister.

    The TunTwister will listen on the given TUN fd.
    The validator is called for each packet *before* twisting. The packet is
    passed in as a scapy packet object, and is the only argument passed to the
    validator.

    Args:
      fd: File descriptor of a TUN interface.
      validator: Function taking one scapy packet object argument.
    """
    self._fd = fd
    # Use a pipe to signal the thread to exit.
    self._signal_read, self._signal_write = os.pipe()
    self._thread = threading.Thread(target=self._RunLoop, name="TunTwister")
    self._validator = validator
    self._error = None

  def __enter__(self):
    self._thread.start()

  def __exit__(self, *args):
    # Signal thread exit.
    os.write(self._signal_write, "bye")
    os.close(self._signal_write)
    self._thread.join(TunTwister._POLL_TIMEOUT_SEC)
    os.close(self._signal_read)
    if self._thread.isAlive():
      raise RuntimeError("Timed out waiting for thread exit")
    # Re-raise any error thrown from our thread.
    if isinstance(self._error, Exception):
      raise self._error  # pylint: disable=raising-bad-type

  def _RunLoop(self):
    """Twist packets until exit signal."""
    try:
      while True:
        read_fds, _, _ = select.select([self._fd, self._signal_read], [], [],
                                       TunTwister._POLL_TIMEOUT_SEC)
        if self._signal_read in read_fds:
          self._Flush()
          return
        if self._fd in read_fds:
          self._ProcessPacket()
    except Exception as e:  # pylint: disable=broad-except
      self._error = e

  def _Flush(self):
    """Ensure no packets are left in the buffer."""
    p = select.poll()
    p.register(self._fd, select.POLLIN)
    while p.poll(TunTwister._POLL_FAST_TIMEOUT_MS):
      self._ProcessPacket()

  def _ProcessPacket(self):
    """Read, twist, and write one packet on the tun/tap."""
    # TODO: Handle EAGAIN "errors".
    bytes_in = os.read(self._fd, TunTwister._READ_BUF_SIZE)
    packet = self.DecodePacket(bytes_in)
    # the user may wish to filter certain packets, such as
    # Ethernet multicast packets
    if self._DropPacket(packet):
      return

    if self._validator:
      self._validator(packet)
    packet = self.TwistPacket(packet)
    os.write(self._fd, packet.build())

  def _DropPacket(self, packet):
    """Determine whether to drop the provided packet by inspection"""
    return False

  @classmethod
  def DecodePacket(cls, bytes_in):
    """Decode a byte array into a scapy object."""
    return cls._DecodeIpPacket(bytes_in)

  @classmethod
  def TwistPacket(cls, packet):
    """Swap the src and dst in the IP header."""
    ip_type = type(packet)
    if ip_type not in (scapy.IP, scapy.IPv6):
      raise TypeError("Expected an IPv4 or IPv6 packet.")
    packet.src, packet.dst = packet.dst, packet.src
    packet = ip_type(packet.build())  # Fix the IP checksum.
    return packet

  @staticmethod
  def _DecodeIpPacket(packet_bytes):
    """Decode 'packet_bytes' as an IPv4 or IPv6 scapy object."""
    ip_ver = (ord(packet_bytes[0]) & 0xF0) >> 4
    if ip_ver == 4:
      return scapy.IP(packet_bytes)
    elif ip_ver == 6:
      return scapy.IPv6(packet_bytes)
    else:
      raise ValueError("packet_bytes is not a valid IPv4 or IPv6 packet")


class TapTwister(TunTwister):
  """Test util for tap interfaces.

  TapTwister works just like TunTwister, except it operates on tap interfaces
  instead of tuns. Ethernet headers will have their sources and destinations
  swapped in addition to IP headers.
  """

  @staticmethod
  def _IsMulticastPacket(eth_pkt):
    return int(eth_pkt.dst.split(":")[0], 16) & 0x1

  def __init__(self, fd=None, validator=None, drop_multicast=True):
    """Construct a TapTwister.

    TapTwister works just like TunTwister, but handles both ethernet and IP
    headers.

    Args:
      fd: File descriptor of a TAP interface.
      validator: Function taking one scapy packet object argument.
      drop_multicast: Drop Ethernet multicast packets
    """
    super(TapTwister, self).__init__(fd=fd, validator=validator)
    self._drop_multicast = drop_multicast

  def _DropPacket(self, packet):
    return self._drop_multicast and self._IsMulticastPacket(packet)

  @classmethod
  def DecodePacket(cls, bytes_in):
    return scapy.Ether(bytes_in)

  @classmethod
  def TwistPacket(cls, packet):
    """Swap the src and dst in the ethernet and IP headers."""
    packet.src, packet.dst = packet.dst, packet.src
    ip_layer = packet.payload
    twisted_ip_layer = super(TapTwister, cls).TwistPacket(ip_layer)
    packet.payload = twisted_ip_layer
    return packet
