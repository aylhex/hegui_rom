/*
 * Copyright (C) 2011 The Android Open Source Project
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

package libcore.android.system;

import android.system.ErrnoException;
import android.system.Int64Ref;
import android.system.NetlinkSocketAddress;
import android.system.Os;
import android.system.OsConstants;
import android.system.PacketSocketAddress;
import android.system.StructRlimit;
import android.system.StructStat;
import android.system.StructTimeval;
import android.system.StructUcred;
import android.system.UnixSocketAddress;

import java.io.File;
import java.io.FileDescriptor;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.FileWriter;
import java.io.IOException;
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.Inet4Address;
import java.net.Inet6Address;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.NetworkInterface;
import java.net.ServerSocket;
import java.net.SocketAddress;
import java.net.SocketException;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.atomic.AtomicReference;

import junit.framework.TestCase;

import libcore.io.IoUtils;

import static android.system.OsConstants.*;

public class OsTest extends TestCase {

    public void testIsSocket() throws Exception {
        File f = new File("/dev/null");
        FileInputStream fis = new FileInputStream(f);
        assertFalse(S_ISSOCK(Os.fstat(fis.getFD()).st_mode));
        fis.close();

        ServerSocket s = new ServerSocket();
        assertTrue(S_ISSOCK(Os.fstat(s.getImpl().getFD$()).st_mode));
        s.close();
    }

    public void testFcntlInt() throws Exception {
        File f = File.createTempFile("OsTest", "tst");
        FileInputStream fis = null;
        try {
            fis = new FileInputStream(f);
            Os.fcntlInt(fis.getFD(), F_SETFD, FD_CLOEXEC);
            int flags = Os.fcntlVoid(fis.getFD(), F_GETFD);
            assertTrue((flags & FD_CLOEXEC) != 0);
        } finally {
            IoUtils.closeQuietly(fis);
            f.delete();
        }
    }

    public void testUnixDomainSockets_in_file_system() throws Exception {
        String path = System.getProperty("java.io.tmpdir") + "/test_unix_socket";
        new File(path).delete();
        checkUnixDomainSocket(UnixSocketAddress.createFileSystem(path), false);
    }

    public void testUnixDomainSocket_abstract_name() throws Exception {
        // Linux treats a sun_path starting with a NUL byte as an abstract name. See unix(7).
        checkUnixDomainSocket(UnixSocketAddress.createAbstract("/abstract_name_unix_socket"), true);
    }

    public void testUnixDomainSocket_unnamed() throws Exception {
        final FileDescriptor fd = Os.socket(AF_UNIX, SOCK_STREAM, 0);
        // unix(7) says an unbound socket is unnamed.
        checkNoSockName(fd);
        Os.close(fd);
    }

    private void checkUnixDomainSocket(final UnixSocketAddress address, final boolean isAbstract)
            throws Exception {
        final FileDescriptor serverFd = Os.socket(AF_UNIX, SOCK_STREAM, 0);
        Os.bind(serverFd, address);
        Os.listen(serverFd, 5);

        checkSockName(serverFd, isAbstract, address);

        Thread server = new Thread(new Runnable() {
            public void run() {
                try {
                    UnixSocketAddress peerAddress = UnixSocketAddress.createUnnamed();
                    FileDescriptor clientFd = Os.accept(serverFd, peerAddress);
                    checkSockName(clientFd, isAbstract, address);
                    checkNoName(peerAddress);

                    checkNoPeerName(clientFd);

                    StructUcred credentials = Os.getsockoptUcred(clientFd, SOL_SOCKET, SO_PEERCRED);
                    assertEquals(Os.getpid(), credentials.pid);
                    assertEquals(Os.getuid(), credentials.uid);
                    assertEquals(Os.getgid(), credentials.gid);

                    byte[] request = new byte[256];
                    Os.read(clientFd, request, 0, request.length);

                    String s = new String(request, "UTF-8");
                    byte[] response = s.toUpperCase(Locale.ROOT).getBytes("UTF-8");
                    Os.write(clientFd, response, 0, response.length);

                    Os.close(clientFd);
                } catch (Exception ex) {
                    throw new RuntimeException(ex);
                }
            }
        });
        server.start();

        FileDescriptor clientFd = Os.socket(AF_UNIX, SOCK_STREAM, 0);

        Os.connect(clientFd, address);
        checkNoSockName(clientFd);

        String string = "hello, world!";

        byte[] request = string.getBytes("UTF-8");
        assertEquals(request.length, Os.write(clientFd, request, 0, request.length));

        byte[] response = new byte[request.length];
        assertEquals(response.length, Os.read(clientFd, response, 0, response.length));

        assertEquals(string.toUpperCase(Locale.ROOT), new String(response, "UTF-8"));

        Os.close(clientFd);
    }

    private static void checkSockName(FileDescriptor fd, boolean isAbstract,
            UnixSocketAddress address) throws Exception {
        UnixSocketAddress isa = (UnixSocketAddress) Os.getsockname(fd);
        assertEquals(address, isa);
        if (isAbstract) {
            assertEquals(0, isa.getSunPath()[0]);
        }
    }

    private void checkNoName(UnixSocketAddress usa) {
        assertEquals(0, usa.getSunPath().length);
    }

    private void checkNoPeerName(FileDescriptor fd) throws Exception {
        checkNoName((UnixSocketAddress) Os.getpeername(fd));
    }

    private void checkNoSockName(FileDescriptor fd) throws Exception {
        checkNoName((UnixSocketAddress) Os.getsockname(fd));
    }

    public void test_strsignal() throws Exception {
        assertEquals("Killed", Os.strsignal(9));
        assertEquals("Unknown signal -1", Os.strsignal(-1));
    }

    public void test_byteBufferPositions_write_pwrite() throws Exception {
        FileOutputStream fos = new FileOutputStream(new File("/dev/null"));
        FileDescriptor fd = fos.getFD();
        final byte[] contents = new String("goodbye, cruel world")
                .getBytes(StandardCharsets.US_ASCII);
        ByteBuffer byteBuffer = ByteBuffer.wrap(contents);

        byteBuffer.position(0);
        int written = Os.write(fd, byteBuffer);
        assertTrue(written > 0);
        assertEquals(written, byteBuffer.position());

        byteBuffer.position(4);
        written = Os.write(fd, byteBuffer);
        assertTrue(written > 0);
        assertEquals(written + 4, byteBuffer.position());

        byteBuffer.position(0);
        written = Os.pwrite(fd, byteBuffer, 64 /* offset */);
        assertTrue(written > 0);
        assertEquals(written, byteBuffer.position());

        byteBuffer.position(4);
        written = Os.pwrite(fd, byteBuffer, 64 /* offset */);
        assertTrue(written > 0);
        assertEquals(written + 4, byteBuffer.position());

        fos.close();
    }

    public void test_byteBufferPositions_read_pread() throws Exception {
        FileInputStream fis = new FileInputStream(new File("/dev/zero"));
        FileDescriptor fd = fis.getFD();
        ByteBuffer byteBuffer = ByteBuffer.allocate(64);

        byteBuffer.position(0);
        int read = Os.read(fd, byteBuffer);
        assertTrue(read > 0);
        assertEquals(read, byteBuffer.position());

        byteBuffer.position(4);
        read = Os.read(fd, byteBuffer);
        assertTrue(read > 0);
        assertEquals(read + 4, byteBuffer.position());

        byteBuffer.position(0);
        read = Os.pread(fd, byteBuffer, 64 /* offset */);
        assertTrue(read > 0);
        assertEquals(read, byteBuffer.position());

        byteBuffer.position(4);
        read = Os.pread(fd, byteBuffer, 64 /* offset */);
        assertTrue(read > 0);
        assertEquals(read + 4, byteBuffer.position());

        fis.close();
    }

    static void checkByteBufferPositions_sendto_recvfrom(
            int family, InetAddress loopback) throws Exception {
        final FileDescriptor serverFd = Os.socket(family, SOCK_STREAM, 0);
        Os.bind(serverFd, loopback, 0);
        Os.listen(serverFd, 5);

        InetSocketAddress address = (InetSocketAddress) Os.getsockname(serverFd);

        final Thread server = new Thread(new Runnable() {
            public void run() {
                try {
                    InetSocketAddress peerAddress = new InetSocketAddress();
                    FileDescriptor clientFd = Os.accept(serverFd, peerAddress);

                    // Attempt to receive a maximum of 24 bytes from the client, and then
                    // close the connection.
                    ByteBuffer buffer = ByteBuffer.allocate(16);
                    int received = Os.recvfrom(clientFd, buffer, 0, null);
                    assertTrue(received > 0);
                    assertEquals(received, buffer.position());

                    ByteBuffer buffer2 = ByteBuffer.allocate(16);
                    buffer2.position(8);
                    received = Os.recvfrom(clientFd, buffer2, 0, null);
                    assertTrue(received > 0);
                    assertEquals(received + 8, buffer.position());

                    Os.close(clientFd);
                } catch (Exception ex) {
                    throw new RuntimeException(ex);
                }
            }
        });

        server.start();

        FileDescriptor clientFd = Os.socket(family, SOCK_STREAM, 0);
        Os.connect(clientFd, address.getAddress(), address.getPort());

        final byte[] bytes = "good bye, cruel black hole with fancy distortion"
                .getBytes(StandardCharsets.US_ASCII);
        assertTrue(bytes.length > 24);

        ByteBuffer input = ByteBuffer.wrap(bytes);
        input.position(0);
        input.limit(16);

        int sent = Os.sendto(clientFd, input, 0, address.getAddress(), address.getPort());
        assertTrue(sent > 0);
        assertEquals(sent, input.position());

        input.position(16);
        input.limit(24);
        sent = Os.sendto(clientFd, input, 0, address.getAddress(), address.getPort());
        assertTrue(sent > 0);
        assertEquals(sent + 16, input.position());

        Os.close(clientFd);
    }

    interface ExceptionalRunnable {

        public void run() throws Exception;
    }

    /**
     * Expects that the given Runnable will throw an exception of the specified class. If the class
     * is ErrnoException, and expectedErrno is non-null, also checks that the errno is equal to
     * expectedErrno.
     */
    private static void expectException(ExceptionalRunnable r, Class<? extends Exception> exClass,
            Integer expectedErrno, String msg) {
        try {
            r.run();
            fail(msg + " did not throw exception");
        } catch (Exception e) {
            assertEquals(msg + " threw unexpected exception", exClass, e.getClass());

            if (expectedErrno != null) {
                if (e instanceof ErrnoException) {
                    assertEquals(msg + "threw ErrnoException with unexpected error number",
                            (int) expectedErrno, ((ErrnoException) e).errno);
                } else {
                    fail("Can only pass expectedErrno when expecting ErrnoException");
                }
            }

        }
    }

    private static void expectBindException(FileDescriptor socket, SocketAddress addr,
            Class exClass, Integer expectedErrno) {
        String msg = String.format("bind(%s, %s)", socket, addr);
        expectException(() -> {
            Os.bind(socket, addr);
        }, exClass, expectedErrno, msg);
    }

    private static void expectConnectException(FileDescriptor socket, SocketAddress addr,
            Class exClass, Integer expectedErrno) {
        String msg = String.format("connect(%s, %s)", socket, addr);
        expectException(() -> {
            Os.connect(socket, addr);
        }, exClass, expectedErrno, msg);
    }

    private static void expectSendtoException(FileDescriptor socket, SocketAddress addr,
            Class exClass, Integer expectedErrno) {
        String msg = String.format("sendto(%s, %s)", socket, addr);
        byte[] packet = new byte[42];
        expectException(() -> {
                    Os.sendto(socket, packet, 0, packet.length, 0, addr);
                },
                exClass, expectedErrno, msg);
    }

    private static void expectBindConnectSendtoSuccess(FileDescriptor socket, String socketDesc,
            SocketAddress addr) {
        String msg = socketDesc + " socket to " + addr.toString();

        try {
            try {
                // Expect that bind throws when any of its arguments are null.
                expectBindException(null, addr, ErrnoException.class, EBADF);
                expectBindException(socket, null, NullPointerException.class, null);
                expectBindException(null, null, NullPointerException.class, null);

                // Expect bind to succeed.
                Os.bind(socket, addr);

                // Find out which port we're actually bound to, and use that in subsequent connect()
                // and send() calls. We can't send to addr because that has a port of 0.
                if (addr instanceof InetSocketAddress) {
                    InetSocketAddress addrISA = (InetSocketAddress) addr;
                    InetSocketAddress socknameISA = (InetSocketAddress) Os.getsockname(socket);

                    assertEquals(addrISA.getAddress(), socknameISA.getAddress());
                    assertEquals(0, addrISA.getPort());
                    assertFalse(0 == socknameISA.getPort());
                    addr = socknameISA;
                }

                // Expect sendto with a null address to throw because the socket is not connected,
                // but to succeed with a non-null address.
                byte[] packet = new byte[42];
                Os.sendto(socket, packet, 0, packet.length, 0, addr);
                // UNIX and IP sockets return different errors for this operation, so we can't check
                // errno.
                expectSendtoException(socket, null, ErrnoException.class, null);
                expectSendtoException(null, null, ErrnoException.class, EBADF);

                // Expect that connect throws when any of its arguments are null.
                expectConnectException(null, addr, ErrnoException.class, EBADF);
                expectConnectException(socket, null, NullPointerException.class, null);
                expectConnectException(null, null, NullPointerException.class, null);

                // Expect connect to succeed.
                Os.connect(socket, addr);
                assertEquals(Os.getsockname(socket), Os.getpeername(socket));

                // Expect sendto to succeed both when given an explicit address and a null address.
                Os.sendto(socket, packet, 0, packet.length, 0, addr);
                Os.sendto(socket, packet, 0, packet.length, 0, null);
            } catch (SocketException | ErrnoException e) {
                fail("Expected success for " + msg + ", but got: " + e);
            }

        } finally {
            IoUtils.closeQuietly(socket);
        }
    }

    private static void expectBindConnectSendtoErrno(int bindErrno, int connectErrno,
            int sendtoErrno, FileDescriptor socket, String socketDesc, SocketAddress addr) {
        try {

            // Expect bind to fail with bindErrno.
            String msg = "bind " + socketDesc + " socket to " + addr.toString();
            try {
                Os.bind(socket, addr);
                fail("Expected to fail " + msg);
            } catch (ErrnoException e) {
                assertEquals("Expected errno " + bindErrno + " " + msg, bindErrno, e.errno);
            } catch (SocketException e) {
                fail("Unexpected SocketException " + msg);
            }

            // Expect connect to fail with connectErrno.
            msg = "connect " + socketDesc + " socket to " + addr.toString();
            try {
                Os.connect(socket, addr);
                fail("Expected to fail " + msg);
            } catch (ErrnoException e) {
                assertEquals("Expected errno " + connectErrno + " " + msg, connectErrno, e.errno);
            } catch (SocketException e) {
                fail("Unexpected SocketException " + msg);
            }

            // Expect sendto to fail with sendtoErrno.
            byte[] packet = new byte[42];
            msg = "sendto " + socketDesc + " socket to " + addr.toString();
            try {
                Os.sendto(socket, packet, 0, packet.length, 0, addr);
                fail("Expected to fail " + msg);
            } catch (ErrnoException e) {
                assertEquals("Expected errno " + sendtoErrno + " " + msg, sendtoErrno, e.errno);
            } catch (SocketException e) {
                fail("Unexpected SocketException " + msg);
            }

        } finally {
            // No matter what happened, close the socket.
            IoUtils.closeQuietly(socket);
        }
    }

    private FileDescriptor makeIpv4Socket() throws Exception {
        return Os.socket(AF_INET, SOCK_DGRAM, 0);
    }

    private FileDescriptor makeIpv6Socket() throws Exception {
        return Os.socket(AF_INET6, SOCK_DGRAM, 0);
    }

    private FileDescriptor makeUnixSocket() throws Exception {
        return Os.socket(AF_UNIX, SOCK_DGRAM, 0);
    }

    public void testCrossFamilyBindConnectSendto() throws Exception {
        SocketAddress addrIpv4 = new InetSocketAddress(InetAddress.getByName("127.0.0.1"), 0);
        SocketAddress addrIpv6 = new InetSocketAddress(InetAddress.getByName("::1"), 0);
        SocketAddress addrUnix = UnixSocketAddress.createAbstract("/abstract_name_unix_socket");

        expectBindConnectSendtoSuccess(makeIpv4Socket(), "ipv4", addrIpv4);
        expectBindConnectSendtoErrno(EAFNOSUPPORT, EAFNOSUPPORT, EAFNOSUPPORT,
                makeIpv4Socket(), "ipv4", addrIpv6);
        expectBindConnectSendtoErrno(EAFNOSUPPORT, EAFNOSUPPORT, EAFNOSUPPORT,
                makeIpv4Socket(), "ipv4", addrUnix);

        // This succeeds because Java always uses dual-stack sockets and all InetAddress and
        // InetSocketAddress objects represent IPv4 addresses using IPv4-mapped IPv6 addresses.
        expectBindConnectSendtoSuccess(makeIpv6Socket(), "ipv6", addrIpv4);
        expectBindConnectSendtoSuccess(makeIpv6Socket(), "ipv6", addrIpv6);
        expectBindConnectSendtoErrno(EAFNOSUPPORT, EAFNOSUPPORT, EINVAL,
                makeIpv6Socket(), "ipv6", addrUnix);

        expectBindConnectSendtoErrno(EINVAL, EINVAL, EINVAL,
                makeUnixSocket(), "unix", addrIpv4);
        expectBindConnectSendtoErrno(EINVAL, EINVAL, EINVAL,
                makeUnixSocket(), "unix", addrIpv6);
        expectBindConnectSendtoSuccess(makeUnixSocket(), "unix", addrUnix);
    }

    public void testUnknownSocketAddressSubclass() throws Exception {
        class MySocketAddress extends SocketAddress {

        }
        MySocketAddress myaddr = new MySocketAddress();

        for (int family : new int[] { AF_INET, AF_INET6, AF_NETLINK }) {
            FileDescriptor s = Os.socket(family, SOCK_DGRAM, 0);
            try {

                try {
                    Os.bind(s, myaddr);
                    fail("bind socket family " + family
                            + " to unknown SocketAddress subclass succeeded");
                } catch (UnsupportedOperationException expected) {
                }

                try {
                    Os.connect(s, myaddr);
                    fail("connect socket family " + family
                            + " to unknown SocketAddress subclass succeeded");
                } catch (UnsupportedOperationException expected) {
                }

                byte[] msg = new byte[42];
                try {
                    Os.sendto(s, msg, 0, msg.length, 0, myaddr);
                    fail("sendto socket family " + family
                            + " to unknown SocketAddress subclass succeeded");
                } catch (UnsupportedOperationException expected) {
                }

            } finally {
                Os.close(s);
            }
        }
    }

    public void test_NetlinkSocket() throws Exception {
        FileDescriptor nlSocket = Os.socket(AF_NETLINK, SOCK_DGRAM, NETLINK_ROUTE);
        Os.bind(nlSocket, new NetlinkSocketAddress());
        NetlinkSocketAddress address = (NetlinkSocketAddress) Os.getsockname(nlSocket);
        assertTrue(address.getPortId() > 0);
        assertEquals(0, address.getGroupsMask());

        NetlinkSocketAddress nlKernel = new NetlinkSocketAddress();
        Os.connect(nlSocket, nlKernel);
        NetlinkSocketAddress nlPeer = (NetlinkSocketAddress) Os.getpeername(nlSocket);
        assertEquals(0, nlPeer.getPortId());
        assertEquals(0, nlPeer.getGroupsMask());
        Os.close(nlSocket);
    }

    public void test_PacketSocketAddress() throws Exception {
        NetworkInterface lo = NetworkInterface.getByName("lo");
        FileDescriptor fd = Os.socket(AF_PACKET, SOCK_DGRAM, ETH_P_IPV6);
        PacketSocketAddress addr = new PacketSocketAddress((short) ETH_P_IPV6, lo.getIndex());
        Os.bind(fd, addr);

        PacketSocketAddress bound = (PacketSocketAddress) Os.getsockname(fd);
        assertEquals((short) ETH_P_IPV6, bound.sll_protocol);  // ETH_P_IPV6 is an int.
        assertEquals(lo.getIndex(), bound.sll_ifindex);
        assertEquals(ARPHRD_LOOPBACK, bound.sll_hatype);
        assertEquals(0, bound.sll_pkttype);

        // The loopback address is ETH_ALEN bytes long and is all zeros.
        // http://lxr.free-electrons.com/source/drivers/net/loopback.c?v=3.10#L167
        assertEquals(6, bound.sll_addr.length);
        for (int i = 0; i < 6; i++) {
            assertEquals(0, bound.sll_addr[i]);
        }
    }

    public void test_byteBufferPositions_sendto_recvfrom_af_inet() throws Exception {
        checkByteBufferPositions_sendto_recvfrom(AF_INET, InetAddress.getByName("127.0.0.1"));
    }

    public void test_byteBufferPositions_sendto_recvfrom_af_inet6() throws Exception {
        checkByteBufferPositions_sendto_recvfrom(AF_INET6, InetAddress.getByName("::1"));
    }

    private void checkSendToSocketAddress(int family, InetAddress loopback) throws Exception {
        FileDescriptor recvFd = Os.socket(family, SOCK_DGRAM, 0);
        Os.bind(recvFd, loopback, 0);
        StructTimeval tv = StructTimeval.fromMillis(20);
        Os.setsockoptTimeval(recvFd, SOL_SOCKET, SO_RCVTIMEO, tv);

        InetSocketAddress to = ((InetSocketAddress) Os.getsockname(recvFd));
        FileDescriptor sendFd = Os.socket(family, SOCK_DGRAM, 0);
        byte[] msg = ("Hello, I'm going to a socket address: " + to.toString()).getBytes("UTF-8");
        int len = msg.length;

        assertEquals(len, Os.sendto(sendFd, msg, 0, len, 0, to));
        byte[] received = new byte[msg.length + 42];
        InetSocketAddress from = new InetSocketAddress();
        assertEquals(len, Os.recvfrom(recvFd, received, 0, received.length, 0, from));
        assertEquals(loopback, from.getAddress());
    }

    public void test_sendtoSocketAddress_af_inet() throws Exception {
        checkSendToSocketAddress(AF_INET, InetAddress.getByName("127.0.0.1"));
    }

    public void test_sendtoSocketAddress_af_inet6() throws Exception {
        checkSendToSocketAddress(AF_INET6, InetAddress.getByName("::1"));
    }

    public void test_socketFamilies() throws Exception {
        FileDescriptor fd = Os.socket(AF_INET6, SOCK_STREAM, 0);
        Os.bind(fd, InetAddress.getByName("::"), 0);
        InetSocketAddress localSocketAddress = (InetSocketAddress) Os.getsockname(fd);
        assertEquals(Inet6Address.ANY, localSocketAddress.getAddress());

        fd = Os.socket(AF_INET6, SOCK_STREAM, 0);
        Os.bind(fd, InetAddress.getByName("0.0.0.0"), 0);
        localSocketAddress = (InetSocketAddress) Os.getsockname(fd);
        assertEquals(Inet6Address.ANY, localSocketAddress.getAddress());

        fd = Os.socket(AF_INET, SOCK_STREAM, 0);
        Os.bind(fd, InetAddress.getByName("0.0.0.0"), 0);
        localSocketAddress = (InetSocketAddress) Os.getsockname(fd);
        assertEquals(Inet4Address.ANY, localSocketAddress.getAddress());
        try {
            Os.bind(fd, InetAddress.getByName("::"), 0);
            fail("Expected ErrnoException binding IPv4 socket to ::");
        } catch (ErrnoException expected) {
            assertEquals("Expected EAFNOSUPPORT binding IPv4 socket to ::", EAFNOSUPPORT,
                    expected.errno);
        }
    }

    private static void assertArrayEquals(byte[] expected, byte[] actual) {
        assertTrue("Expected=" + Arrays.toString(expected) + ", actual=" + Arrays.toString(actual),
                Arrays.equals(expected, actual));
    }

    private static void checkSocketPing(FileDescriptor fd, InetAddress to, byte[] packet,
            byte type, byte responseType, boolean useSendto) throws Exception {
        int len = packet.length;
        packet[0] = type;
        if (useSendto) {
            assertEquals(len, Os.sendto(fd, packet, 0, len, 0, to, 0));
        } else {
            Os.connect(fd, to, 0);
            assertEquals(len, Os.sendto(fd, packet, 0, len, 0, null, 0));
        }

        int icmpId = ((InetSocketAddress) Os.getsockname(fd)).getPort();
        byte[] received = new byte[4096];
        InetSocketAddress srcAddress = new InetSocketAddress();
        assertEquals(len, Os.recvfrom(fd, received, 0, received.length, 0, srcAddress));
        assertEquals(to, srcAddress.getAddress());
        assertEquals(responseType, received[0]);
        assertEquals(received[4], (byte) (icmpId >> 8));
        assertEquals(received[5], (byte) (icmpId & 0xff));

        received = Arrays.copyOf(received, len);
        received[0] = (byte) type;
        received[2] = received[3] = 0;  // Checksum.
        received[4] = received[5] = 0;  // ICMP ID.
        assertArrayEquals(packet, received);
    }

    public void test_socketPing() throws Exception {
        final byte ICMP_ECHO = 8, ICMP_ECHOREPLY = 0;
        final byte ICMPV6_ECHO_REQUEST = (byte) 128, ICMPV6_ECHO_REPLY = (byte) 129;
        final byte[] packet = ("\000\000\000\000" +  // ICMP type, code.
                "\000\000\000\003" +  // ICMP ID (== port), sequence number.
                "Hello myself").getBytes(StandardCharsets.US_ASCII);

        FileDescriptor fd = Os.socket(AF_INET6, SOCK_DGRAM, IPPROTO_ICMPV6);
        InetAddress ipv6Loopback = InetAddress.getByName("::1");
        checkSocketPing(fd, ipv6Loopback, packet, ICMPV6_ECHO_REQUEST, ICMPV6_ECHO_REPLY, true);
        checkSocketPing(fd, ipv6Loopback, packet, ICMPV6_ECHO_REQUEST, ICMPV6_ECHO_REPLY, false);

        fd = Os.socket(AF_INET, SOCK_DGRAM, IPPROTO_ICMP);
        InetAddress ipv4Loopback = InetAddress.getByName("127.0.0.1");
        checkSocketPing(fd, ipv4Loopback, packet, ICMP_ECHO, ICMP_ECHOREPLY, true);
        checkSocketPing(fd, ipv4Loopback, packet, ICMP_ECHO, ICMP_ECHOREPLY, false);
    }

    public void test_Ipv4Fallback() throws Exception {
        // This number of iterations gives a ~60% chance of creating the conditions that caused
        // http://b/23088314 without making test times too long. On a hammerhead running MRZ37C
        // using vogar, this test takes about 4s.
        final int ITERATIONS = 10000;
        for (int i = 0; i < ITERATIONS; i++) {
            FileDescriptor mUdpSock = Os.socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
            try {
                Os.bind(mUdpSock, Inet4Address.ANY, 0);
            } catch (ErrnoException e) {
                fail("ErrnoException after " + i + " iterations: " + e);
            } finally {
                Os.close(mUdpSock);
            }
        }
    }

    public void test_unlink() throws Exception {
        File f = File.createTempFile("OsTest", "tst");
        assertTrue(f.exists());
        Os.unlink(f.getAbsolutePath());
        assertFalse(f.exists());

        try {
            Os.unlink(f.getAbsolutePath());
            fail();
        } catch (ErrnoException e) {
            assertEquals(OsConstants.ENOENT, e.errno);
        }
    }

    // b/27294715
    public void test_recvfrom_concurrentShutdown() throws Exception {
        final FileDescriptor serverFd = Os.socket(AF_INET, SOCK_DGRAM, 0);
        Os.bind(serverFd, InetAddress.getByName("127.0.0.1"), 0);
        // Set 4s timeout
        StructTimeval tv = StructTimeval.fromMillis(4000);
        Os.setsockoptTimeval(serverFd, SOL_SOCKET, SO_RCVTIMEO, tv);

        final AtomicReference<Exception> killerThreadException = new AtomicReference<Exception>(
                null);
        final Thread killer = new Thread(new Runnable() {
            public void run() {
                try {
                    Thread.sleep(2000);
                    try {
                        Os.shutdown(serverFd, SHUT_RDWR);
                    } catch (ErrnoException expected) {
                        if (OsConstants.ENOTCONN != expected.errno) {
                            killerThreadException.set(expected);
                        }
                    }
                } catch (Exception ex) {
                    killerThreadException.set(ex);
                }
            }
        });
        killer.start();

        ByteBuffer buffer = ByteBuffer.allocate(16);
        InetSocketAddress srcAddress = new InetSocketAddress();
        int received = Os.recvfrom(serverFd, buffer, 0, srcAddress);
        assertTrue(received == 0);
        Os.close(serverFd);

        killer.join();
        assertNull(killerThreadException.get());
    }

    public void test_xattr() throws Exception {
        final String NAME_TEST = "user.meow";

        final byte[] VALUE_CAKE = "cake cake cake".getBytes(StandardCharsets.UTF_8);
        final byte[] VALUE_PIE = "pie".getBytes(StandardCharsets.UTF_8);

        File file = File.createTempFile("xattr", "test");
        String path = file.getAbsolutePath();

        try {
            try {
                Os.getxattr(path, NAME_TEST);
                fail("Expected ENODATA");
            } catch (ErrnoException e) {
                assertEquals(OsConstants.ENODATA, e.errno);
            }
            assertFalse(Arrays.asList(Os.listxattr(path)).contains(NAME_TEST));

            Os.setxattr(path, NAME_TEST, VALUE_CAKE, OsConstants.XATTR_CREATE);
            byte[] xattr_create = Os.getxattr(path, NAME_TEST);
            assertTrue(Arrays.asList(Os.listxattr(path)).contains(NAME_TEST));
            assertEquals(VALUE_CAKE.length, xattr_create.length);
            assertStartsWith(VALUE_CAKE, xattr_create);

            try {
                Os.setxattr(path, NAME_TEST, VALUE_PIE, OsConstants.XATTR_CREATE);
                fail("Expected EEXIST");
            } catch (ErrnoException e) {
                assertEquals(OsConstants.EEXIST, e.errno);
            }

            Os.setxattr(path, NAME_TEST, VALUE_PIE, OsConstants.XATTR_REPLACE);
            byte[] xattr_replace = Os.getxattr(path, NAME_TEST);
            assertTrue(Arrays.asList(Os.listxattr(path)).contains(NAME_TEST));
            assertEquals(VALUE_PIE.length, xattr_replace.length);
            assertStartsWith(VALUE_PIE, xattr_replace);

            Os.removexattr(path, NAME_TEST);
            try {
                Os.getxattr(path, NAME_TEST);
                fail("Expected ENODATA");
            } catch (ErrnoException e) {
                assertEquals(OsConstants.ENODATA, e.errno);
            }
            assertFalse(Arrays.asList(Os.listxattr(path)).contains(NAME_TEST));

        } finally {
            file.delete();
        }
    }

    public void test_xattr_NPE() throws Exception {
        File file = File.createTempFile("xattr", "test");
        final String path = file.getAbsolutePath();
        final String NAME_TEST = "user.meow";
        final byte[] VALUE_CAKE = "cake cake cake".getBytes(StandardCharsets.UTF_8);

        // getxattr
        try {
            Os.getxattr(null, NAME_TEST);
            fail();
        } catch (NullPointerException expected) {
        }
        try {
            Os.getxattr(path, null);
            fail();
        } catch (NullPointerException expected) {
        }

        // listxattr
        try {
            Os.listxattr(null);
            fail();
        } catch (NullPointerException expected) {
        }

        // removexattr
        try {
            Os.removexattr(null, NAME_TEST);
            fail();
        } catch (NullPointerException expected) {
        }
        try {
            Os.removexattr(path, null);
            fail();
        } catch (NullPointerException expected) {
        }

        // setxattr
        try {
            Os.setxattr(null, NAME_TEST, VALUE_CAKE, OsConstants.XATTR_CREATE);
            fail();
        } catch (NullPointerException expected) {
        }
        try {
            Os.setxattr(path, null, VALUE_CAKE, OsConstants.XATTR_CREATE);
            fail();
        } catch (NullPointerException expected) {
        }
        try {
            Os.setxattr(path, NAME_TEST, null, OsConstants.XATTR_CREATE);
            fail();
        } catch (NullPointerException expected) {
        }
    }

    public void test_xattr_Errno() throws Exception {
        final String NAME_TEST = "user.meow";
        final byte[] VALUE_CAKE = "cake cake cake".getBytes(StandardCharsets.UTF_8);

        // ENOENT, No such file or directory.
        try {
            Os.getxattr("", NAME_TEST);
            fail();
        } catch (ErrnoException e) {
            assertEquals(ENOENT, e.errno);
        }
        try {
            Os.listxattr("");
            fail();
        } catch (ErrnoException e) {
            assertEquals(ENOENT, e.errno);
        }
        try {
            Os.removexattr("", NAME_TEST);
            fail();
        } catch (ErrnoException e) {
            assertEquals(ENOENT, e.errno);
        }
        try {
            Os.setxattr("", NAME_TEST, VALUE_CAKE, OsConstants.XATTR_CREATE);
            fail();
        } catch (ErrnoException e) {
            assertEquals(ENOENT, e.errno);
        }

        // ENOTSUP, Extended attributes are not supported by the filesystem, or are disabled.
        // Since kernel version 4.9 (or some other version after 4.4), *xattr() methods
        // may set errno to EACCESS instead. This behavior change is likely related to
        // https://patchwork.kernel.org/patch/9294421/ which reimplemented getxattr, setxattr,
        // and removexattr on top of generic handlers.
        final String path = "/proc/self/stat";
        try {
            Os.setxattr(path, NAME_TEST, VALUE_CAKE, OsConstants.XATTR_CREATE);
            fail();
        } catch (ErrnoException e) {
            assertTrue("Unexpected errno: " + e.errno, e.errno == ENOTSUP || e.errno == EACCES);
        }
        try {
            Os.getxattr(path, NAME_TEST);
            fail();
        } catch (ErrnoException e) {
            assertEquals(ENOTSUP, e.errno);
        }
        try {
            // Linux listxattr does not set errno.
            Os.listxattr(path);
        } catch (ErrnoException e) {
            fail();
        }
        try {
            Os.removexattr(path, NAME_TEST);
            fail();
        } catch (ErrnoException e) {
            assertTrue("Unexpected errno: " + e.errno, e.errno == ENOTSUP || e.errno == EACCES);
        }
    }

    public void test_realpath() throws Exception {
        File tmpDir = new File(System.getProperty("java.io.tmpdir"));
        // This is a chicken and egg problem. We have no way of knowing whether
        // the temporary directory or one of its path elements were symlinked, so
        // we'll need this call to realpath.
        String canonicalTmpDir = Os.realpath(tmpDir.getAbsolutePath());

        // Test that "." and ".." are resolved correctly.
        assertEquals(canonicalTmpDir,
                Os.realpath(canonicalTmpDir + "/./../" + tmpDir.getName()));

        // Test that symlinks are resolved correctly.
        File target = new File(tmpDir, "target");
        File link = new File(tmpDir, "link");
        try {
            assertTrue(target.createNewFile());
            Os.symlink(target.getAbsolutePath(), link.getAbsolutePath());

            assertEquals(canonicalTmpDir + "/target",
                    Os.realpath(canonicalTmpDir + "/link"));
        } finally {
            boolean deletedTarget = target.delete();
            boolean deletedLink = link.delete();
            // Asserting this here to provide a definitive reason for
            // a subsequent failure on the same run.
            assertTrue("deletedTarget = " + deletedTarget + ", deletedLink =" + deletedLink,
                    deletedTarget && deletedLink);
        }
    }

    /**
     * Tests that TCP_USER_TIMEOUT can be set on a TCP socket, but doesn't test
     * that it behaves as expected.
     */
    public void test_socket_tcpUserTimeout_setAndGet() throws Exception {
        final FileDescriptor fd = Os.socket(AF_INET, SOCK_STREAM, 0);
        try {
            int v = Os.getsockoptInt(fd, OsConstants.IPPROTO_TCP, OsConstants.TCP_USER_TIMEOUT);
            assertEquals(0, v); // system default value
            int newValue = 3000;
            Os.setsockoptInt(fd, OsConstants.IPPROTO_TCP, OsConstants.TCP_USER_TIMEOUT,
                    newValue);
            int actualValue = Os.getsockoptInt(fd, OsConstants.IPPROTO_TCP,
                    OsConstants.TCP_USER_TIMEOUT);
            // The kernel can round the requested value based on the HZ setting. We allow up to 10ms
            // difference.
            assertTrue("Returned incorrect timeout:" + actualValue,
                    Math.abs(newValue - actualValue) <= 10);
            // No need to reset the value to 0, since we're throwing the socket away
        } finally {
            Os.close(fd);
        }
    }

    public void test_socket_tcpUserTimeout_doesNotWorkOnDatagramSocket() throws Exception {
        final FileDescriptor fd = Os.socket(AF_INET, SOCK_DGRAM, 0);
        try {
            Os.setsockoptInt(fd, OsConstants.IPPROTO_TCP, OsConstants.TCP_USER_TIMEOUT,
                    3000);
            fail("datagram (connectionless) sockets shouldn't support TCP_USER_TIMEOUT");
        } catch (ErrnoException expected) {
            // expected
        } finally {
            Os.close(fd);
        }
    }

    public void test_socket_sockoptTimeval_readWrite() throws Exception {
        FileDescriptor fd = Os.socket(AF_INET6, SOCK_STREAM, 0);
        try {
            StructTimeval v = Os.getsockoptTimeval(fd, SOL_SOCKET, SO_RCVTIMEO);
            assertEquals(0, v.toMillis()); // system default value

            StructTimeval newValue = StructTimeval.fromMillis(3000);
            Os.setsockoptTimeval(fd, SOL_SOCKET, SO_RCVTIMEO, newValue);

            StructTimeval actualValue = Os.getsockoptTimeval(fd, SOL_SOCKET, SO_RCVTIMEO);

            // The kernel can round the requested value based on the HZ setting. We allow up to 10ms
            // difference.
            assertTrue("Returned incorrect timeout:" + actualValue,
                    Math.abs(newValue.toMillis() - actualValue.toMillis()) <= 10);
            // No need to reset the value to 0, since we're throwing the socket away
        } finally {
            Os.close(fd);
        }
    }

    public void test_socket_setSockoptTimeval_effective() throws Exception {
        int timeoutValueMillis = 50;
        int allowedTimeoutMillis = 500;

        FileDescriptor fd = Os.socket(AF_INET6, SOCK_DGRAM, IPPROTO_UDP);
        try {
            StructTimeval tv = StructTimeval.fromMillis(timeoutValueMillis);
            Os.setsockoptTimeval(fd, SOL_SOCKET, SO_RCVTIMEO, tv);
            Os.bind(fd, InetAddress.getByName("::1"), 0);

            byte[] request = new byte[1];
            long startTime = System.nanoTime();
            expectException(() -> Os.read(fd, request, 0, request.length),
                    ErrnoException.class, EAGAIN, "Expected timeout");
            long endTime = System.nanoTime();
            assertTrue(Duration.ofNanos(endTime - startTime).toMillis() < allowedTimeoutMillis);
        } finally {
            Os.close(fd);
        }
    }

    public void test_socket_setSockoptTimeval_nullFd() throws Exception {
        StructTimeval tv = StructTimeval.fromMillis(500);
        expectException(
                () -> Os.setsockoptTimeval(null, SOL_SOCKET, SO_RCVTIMEO, tv),
                ErrnoException.class, EBADF, "setsockoptTimeval(null, ...)");
    }

    public void test_socket_setSockoptTimeval_fileFd() throws Exception {
        File testFile = createTempFile("test_socket_setSockoptTimeval_invalidFd", "");
        try (FileInputStream fis = new FileInputStream(testFile)) {
            final FileDescriptor fd = fis.getFD();

            StructTimeval tv = StructTimeval.fromMillis(500);
            expectException(
                    () -> Os.setsockoptTimeval(fd, SOL_SOCKET, SO_RCVTIMEO, tv),
                    ErrnoException.class, ENOTSOCK, "setsockoptTimeval(<file fd>, ...)");
        }
    }

    public void test_socket_setSockoptTimeval_badFd() throws Exception {
        StructTimeval tv = StructTimeval.fromMillis(500);
        FileDescriptor invalidFd = Os.socket(AF_INET6, SOCK_STREAM, 0);
        Os.close(invalidFd);

        expectException(
                () -> Os.setsockoptTimeval(invalidFd, SOL_SOCKET, SO_RCVTIMEO, tv),
                ErrnoException.class, EBADF, "setsockoptTimeval(<closed fd>, ...)");
    }

    public void test_socket_setSockoptTimeval_invalidLevel() throws Exception {
        StructTimeval tv = StructTimeval.fromMillis(500);
        FileDescriptor fd = Os.socket(AF_INET6, SOCK_STREAM, 0);
        try {
            expectException(
                    () -> Os.setsockoptTimeval(fd, -1, SO_RCVTIMEO, tv),
                    ErrnoException.class, ENOPROTOOPT,
                    "setsockoptTimeval(fd, <invalid level>, ...)");
        } finally {
            Os.close(fd);
        }
    }

    public void test_socket_setSockoptTimeval_invalidOpt() throws Exception {
        StructTimeval tv = StructTimeval.fromMillis(500);
        FileDescriptor fd = Os.socket(AF_INET6, SOCK_STREAM, 0);
        try {
            expectException(
                    () -> Os.setsockoptTimeval(fd, SOL_SOCKET, -1, tv),
                    ErrnoException.class, ENOPROTOOPT,
                    "setsockoptTimeval(fd, <invalid level>, ...)");
        } finally {
            Os.close(fd);
        }
    }

    public void test_socket_setSockoptTimeval_nullTimeVal() throws Exception {
        FileDescriptor fd = Os.socket(AF_INET6, SOCK_STREAM, 0);
        try {
            expectException(
                    () -> Os.setsockoptTimeval(fd, SOL_SOCKET, SO_RCVTIMEO, null),
                    NullPointerException.class, null, "setsockoptTimeval(..., null)");
        } finally {
            Os.close(fd);
        }
    }

    public void test_socket_getSockoptTimeval_invalidOption() throws Exception {
        FileDescriptor fd = Os.socket(AF_INET6, SOCK_STREAM, 0);
        try {
            expectException(
                    () -> Os.getsockoptTimeval(fd, SOL_SOCKET, SO_DEBUG),
                    IllegalArgumentException.class, null,
                    "getsockoptTimeval(..., <non-timeval option>)");
        } finally {
            Os.close(fd);
        }
    }

    public void test_if_nametoindex_if_indextoname() throws Exception {
        List<NetworkInterface> nis = Collections.list(NetworkInterface.getNetworkInterfaces());

        assertTrue(nis.size() > 0);
        for (NetworkInterface ni : nis) {
            int index = ni.getIndex();
            String name = ni.getName();
            assertEquals(index, Os.if_nametoindex(name));
            assertTrue(Os.if_indextoname(index).equals(name));
        }

        assertEquals(0, Os.if_nametoindex("this-interface-does-not-exist"));
        assertEquals(null, Os.if_indextoname(-1000));

        try {
            Os.if_nametoindex(null);
            fail();
        } catch (NullPointerException expected) {
        }
    }

    private static void assertStartsWith(byte[] expectedContents, byte[] container) {
        for (int i = 0; i < expectedContents.length; i++) {
            if (expectedContents[i] != container[i]) {
                fail("Expected " + Arrays.toString(expectedContents) + " but found "
                        + Arrays.toString(expectedContents));
            }
        }
    }

    public void test_readlink() throws Exception {
        File path = new File(IoUtils.createTemporaryDirectory("test_readlink"), "symlink");

        // ext2 and ext4 have PAGE_SIZE limits on symlink targets.
        // If file encryption is enabled, there's extra overhead to store the
        // size of the encrypted symlink target. There's also an off-by-one
        // in current kernels (and marlin/sailfish where we're seeing this
        // failure are still on 3.18, far from current). Given that we don't
        // really care here, just use 2048 instead. http://b/33306057.
        int size = 2048;
        String xs = "";
        for (int i = 0; i < size - 1; ++i) {
            xs += "x";
        }

        Os.symlink(xs, path.getPath());

        assertEquals(xs, Os.readlink(path.getPath()));
    }

    // Address should be correctly set for empty packets. http://b/33481605
    public void test_recvfrom_EmptyPacket() throws Exception {
        try (DatagramSocket ds = new DatagramSocket();
             DatagramSocket srcSock = new DatagramSocket()) {
            srcSock.send(new DatagramPacket(new byte[0], 0, ds.getLocalSocketAddress()));

            byte[] recvBuf = new byte[16];
            InetSocketAddress address = new InetSocketAddress();
            int recvCount =
                    android.system.Os.recvfrom(ds.getFileDescriptor$(), recvBuf, 0, 16, 0, address);
            assertEquals(0, recvCount);
            assertTrue(address.getAddress().isLoopbackAddress());
            assertEquals(srcSock.getLocalPort(), address.getPort());
        }
    }

    public void test_fstat_times() throws Exception {
        File file = File.createTempFile("OsTest", "fstattest");
        FileOutputStream fos = new FileOutputStream(file);
        StructStat structStat1 = Os.fstat(fos.getFD());
        assertEquals(structStat1.st_mtim.tv_sec, structStat1.st_mtime);
        assertEquals(structStat1.st_ctim.tv_sec, structStat1.st_ctime);
        assertEquals(structStat1.st_atim.tv_sec, structStat1.st_atime);
        Thread.sleep(100);
        fos.write(new byte[] { 1, 2, 3 });
        fos.flush();
        StructStat structStat2 = Os.fstat(fos.getFD());
        fos.close();

        assertEquals(-1, structStat1.st_mtim.compareTo(structStat2.st_mtim));
        assertEquals(-1, structStat1.st_ctim.compareTo(structStat2.st_ctim));
        assertEquals(0, structStat1.st_atim.compareTo(structStat2.st_atim));
    }

    public void test_getrlimit() throws Exception {
        StructRlimit rlimit = Os.getrlimit(OsConstants.RLIMIT_NOFILE);
        // We can't really make any assertions about these values since they might vary from
        // device to device and even process to process. We do know that they will be greater
        // than zero, though.
        assertTrue(rlimit.rlim_cur > 0);
        assertTrue(rlimit.rlim_max > 0);
    }

    // http://b/65051835
    public void test_pipe2_errno() throws Exception {
        try {
            // flag=-1 is not a valid value for pip2, will EINVAL
            Os.pipe2(-1);
            fail();
        } catch (ErrnoException expected) {
        }
    }

    // http://b/65051835
    public void test_sendfile_errno() throws Exception {
        try {
            // FileDescriptor.out is not open for input, will cause EBADF
            Int64Ref offset = new Int64Ref(10);
            Os.sendfile(FileDescriptor.out, FileDescriptor.out, offset, 10);
            fail();
        } catch (ErrnoException expected) {
        }
    }

    public void test_sendfile_null() throws Exception {
        File in = createTempFile("test_sendfile_null", "Hello, world!");
        try {
            int len = "Hello".length();
            assertEquals("Hello", checkSendfile(in, null, len, null));
        } finally {
            in.delete();
        }
    }

    public void test_sendfile_offset() throws Exception {
        File in = createTempFile("test_sendfile_offset", "Hello, world!");
        try {
            // checkSendfile(sendFileImplToUse, in, startOffset, maxBytes, expectedEndOffset)
            assertEquals("Hello", checkSendfile(in, 0L, 5, 5L));
            assertEquals("ello,", checkSendfile(in, 1L, 5, 6L));
            // At offset 9, only 4 bytes/chars available, even though we're asking for 5.
            assertEquals("rld!", checkSendfile(in, 9L, 5, 13L));
            assertEquals("", checkSendfile(in, 1L, 0, 1L));
        } finally {
            in.delete();
        }
    }

    private static String checkSendfile(File in, Long startOffset,
            int maxBytes, Long expectedEndOffset) throws IOException, ErrnoException {
        File out = File.createTempFile(OsTest.class.getSimpleName() + "_checkSendFile", ".out");
        try (FileInputStream inStream = new FileInputStream(in)) {
            FileDescriptor inFd = inStream.getFD();
            try (FileOutputStream outStream = new FileOutputStream(out)) {
                FileDescriptor outFd = outStream.getFD();
                Int64Ref offset = (startOffset == null) ? null : new Int64Ref(startOffset);
                android.system.Os.sendfile(outFd, inFd, offset, maxBytes);
                assertEquals(expectedEndOffset, offset == null ? null : offset.value);
            }
            return IoUtils.readFileAsString(out.getPath());
        } finally {
            out.delete();
        }
    }

    private static File createTempFile(String namePart, String contents) throws IOException {
        File f = File.createTempFile(OsTest.class.getSimpleName() + namePart, ".in");
        try (FileWriter writer = new FileWriter(f)) {
            writer.write(contents);
        }
        return f;
    }

    public void test_odirect() throws Exception {
        File testFile = createTempFile("test_odirect", "");
        try {
            FileDescriptor fd =
                    Os.open(testFile.toString(), O_WRONLY | O_DIRECT, S_IRUSR | S_IWUSR);
            assertNotNull(fd);
            assertTrue(fd.valid());
            int flags = Os.fcntlVoid(fd, F_GETFL);
            assertTrue("Expected file flags to include " + O_DIRECT + ", actual value: " + flags,
                    0 != (flags & O_DIRECT));
            Os.close(fd);
        } finally {
            testFile.delete();
        }
    }

    public void test_splice() throws Exception {
        FileDescriptor[] pipe = Os.pipe2(0);
        File in = createTempFile("splice1", "foobar");
        File out = createTempFile("splice2", "");

        Int64Ref offIn = new Int64Ref(1);
        Int64Ref offOut = new Int64Ref(0);

        // Splice into pipe
        try (FileInputStream streamIn = new FileInputStream(in)) {
            FileDescriptor fdIn = streamIn.getFD();
            long result = Os
                    .splice(fdIn, offIn, pipe[1], null /* offOut */, 10 /* len */, 0 /* flags */);
            assertEquals(5, result);
            assertEquals(6, offIn.value);
        }

        // Splice from pipe
        try (FileOutputStream streamOut = new FileOutputStream(out)) {
            FileDescriptor fdOut = streamOut.getFD();
            long result = Os
                    .splice(pipe[0], null /* offIn */, fdOut, offOut, 10 /* len */, 0 /* flags */);
            assertEquals(5, result);
            assertEquals(5, offOut.value);
        }

        assertEquals("oobar", IoUtils.readFileAsString(out.getPath()));

        Os.close(pipe[0]);
        Os.close(pipe[1]);
    }

    public void test_splice_errors() throws Exception {
        File in = createTempFile("splice3", "");
        File out = createTempFile("splice4", "");
        FileDescriptor[] pipe = Os.pipe2(0);

        //.fdIn == null
        try {
            Os.splice(null /* fdIn */, null /* offIn */, pipe[1],
                    null /*offOut*/, 10 /* len */, 0 /* flags */);
            fail();
        } catch (ErrnoException expected) {
            assertEquals(EBADF, expected.errno);
        }

        //.fdOut == null
        try {
            Os.splice(pipe[0] /* fdIn */, null /* offIn */, null  /* fdOut */,
                    null /*offOut*/, 10 /* len */, 0 /* flags */);
            fail();
        } catch (ErrnoException expected) {
            assertEquals(EBADF, expected.errno);
        }

        // No pipe fd
        try (FileOutputStream streamOut = new FileOutputStream(out)) {
            try (FileInputStream streamIn = new FileInputStream(in)) {
                FileDescriptor fdIn = streamIn.getFD();
                FileDescriptor fdOut = streamOut.getFD();
                Os.splice(fdIn, null  /* offIn */, fdOut, null /* offOut */, 10 /* len */,
                        0 /* flags */);
                fail();
            } catch (ErrnoException expected) {
                assertEquals(EINVAL, expected.errno);
            }
        }

        Os.close(pipe[0]);
        Os.close(pipe[1]);
    }

    public void testCloseNullFileDescriptor() throws Exception {
        try {
            Os.close(null);
            fail();
        } catch (NullPointerException expected) {
        }
    }

    public void testSocketpairNullFileDescriptor1() throws Exception {
        try {
            Os.socketpair(AF_UNIX, SOCK_STREAM, 0, null, new FileDescriptor());
            fail();
        } catch (NullPointerException expected) {
        }
    }

    public void testSocketpairNullFileDescriptor2() throws Exception {
        try {
            Os.socketpair(AF_UNIX, SOCK_STREAM, 0, new FileDescriptor(), null);
            fail();
        } catch (NullPointerException expected) {
        }
    }

    public void testSocketpairNullFileDescriptorBoth() throws Exception {
        try {
            Os.socketpair(AF_UNIX, SOCK_STREAM, 0, null, null);
            fail();
        } catch (NullPointerException expected) {
        }
    }

    public void testInetPtonIpv4() {
        String srcAddress = "127.0.0.1";
        InetAddress inetAddress = Os.inet_pton(AF_INET, srcAddress);
        assertEquals(srcAddress, inetAddress.getHostAddress());
    }

    public void testInetPtonIpv6() {
        String srcAddress = "1123:4567:89ab:cdef:fedc:ba98:7654:3210";
        InetAddress inetAddress = Os.inet_pton(AF_INET6, srcAddress);
        assertEquals(srcAddress, inetAddress.getHostAddress());
    }

    public void testInetPtonInvalidFamily() {
        String srcAddress = "127.0.0.1";
        InetAddress inetAddress = Os.inet_pton(AF_UNIX, srcAddress);
        assertNull(inetAddress);
    }

    public void testInetPtonWrongFamily() {
        String srcAddress = "127.0.0.1";
        InetAddress inetAddress = Os.inet_pton(AF_INET6, srcAddress);
        assertNull(inetAddress);
    }

    public void testInetPtonInvalidData() {
        String srcAddress = "10.1";
        InetAddress inetAddress = Os.inet_pton(AF_INET, srcAddress);
        assertNull(inetAddress);
    }
}
