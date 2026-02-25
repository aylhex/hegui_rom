/*
 * Copyright (C) 2014 The Android Open Source Project
 * Copyright (c) 1996, 2013, Oracle and/or its affiliates. All rights reserved.
 * DO NOT ALTER OR REMOVE COPYRIGHT NOTICES OR THIS FILE HEADER.
 *
 * This code is free software; you can redistribute it and/or modify it
 * under the terms of the GNU General Public License version 2 only, as
 * published by the Free Software Foundation.  Oracle designates this
 * particular file as subject to the "Classpath" exception as provided
 * by Oracle in the LICENSE file that accompanied this code.
 *
 * This code is distributed in the hope that it will be useful, but WITHOUT
 * ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
 * FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General Public License
 * version 2 for more details (a copy is included in the LICENSE file that
 * accompanied this code).
 *
 * You should have received a copy of the GNU General Public License version
 * 2 along with this work; if not, write to the Free Software Foundation,
 * Inc., 51 Franklin St, Fifth Floor, Boston, MA 02110-1301 USA.
 *
 * Please contact Oracle, 500 Oracle Parkway, Redwood Shores, CA 94065 USA
 * or visit www.oracle.com if you need additional information or have any
 * questions.
 */


package sun.security.pkcs;

import java.io.*;
import java.util.*;
import java.security.*;
import sun.security.util.*;
import sun.security.x509.AlgorithmId;
import sun.security.x509.X500Name;

@libcore.api.CorePlatformApi
@libcore.api.Hide
@SuppressWarnings({"unchecked", "deprecation", "all"})
public class PKCS7 {

@libcore.api.CorePlatformApi
public PKCS7(java.io.InputStream in) throws java.io.IOException, sun.security.pkcs.ParsingException { throw new RuntimeException("Stub!"); }

public PKCS7(sun.security.util.DerInputStream derin) throws sun.security.pkcs.ParsingException { throw new RuntimeException("Stub!"); }

@libcore.api.CorePlatformApi
public PKCS7(byte[] bytes) throws sun.security.pkcs.ParsingException { throw new RuntimeException("Stub!"); }

public PKCS7(sun.security.x509.AlgorithmId[] digestAlgorithmIds, sun.security.pkcs.ContentInfo contentInfo, java.security.cert.X509Certificate[] certificates, java.security.cert.X509CRL[] crls, sun.security.pkcs.SignerInfo[] signerInfos) { throw new RuntimeException("Stub!"); }

public PKCS7(sun.security.x509.AlgorithmId[] digestAlgorithmIds, sun.security.pkcs.ContentInfo contentInfo, java.security.cert.X509Certificate[] certificates, sun.security.pkcs.SignerInfo[] signerInfos) { throw new RuntimeException("Stub!"); }

public void encodeSignedData(java.io.OutputStream out) throws java.io.IOException { throw new RuntimeException("Stub!"); }

public void encodeSignedData(sun.security.util.DerOutputStream out) throws java.io.IOException { throw new RuntimeException("Stub!"); }

public sun.security.pkcs.SignerInfo verify(sun.security.pkcs.SignerInfo info, byte[] bytes) throws java.security.NoSuchAlgorithmException, java.security.SignatureException { throw new RuntimeException("Stub!"); }

@libcore.api.CorePlatformApi
public sun.security.pkcs.SignerInfo verify(sun.security.pkcs.SignerInfo info, java.io.InputStream dataInputStream) throws java.io.IOException, java.security.NoSuchAlgorithmException, java.security.SignatureException { throw new RuntimeException("Stub!"); }

@libcore.api.CorePlatformApi
public sun.security.pkcs.SignerInfo[] verify(byte[] bytes) throws java.security.NoSuchAlgorithmException, java.security.SignatureException { throw new RuntimeException("Stub!"); }

public sun.security.pkcs.SignerInfo[] verify() throws java.security.NoSuchAlgorithmException, java.security.SignatureException { throw new RuntimeException("Stub!"); }

public java.math.BigInteger getVersion() { throw new RuntimeException("Stub!"); }

public sun.security.x509.AlgorithmId[] getDigestAlgorithmIds() { throw new RuntimeException("Stub!"); }

@libcore.api.CorePlatformApi
public sun.security.pkcs.ContentInfo getContentInfo() { throw new RuntimeException("Stub!"); }

@libcore.api.CorePlatformApi
public java.security.cert.X509Certificate[] getCertificates() { throw new RuntimeException("Stub!"); }

public java.security.cert.X509CRL[] getCRLs() { throw new RuntimeException("Stub!"); }

@libcore.api.CorePlatformApi
public sun.security.pkcs.SignerInfo[] getSignerInfos() { throw new RuntimeException("Stub!"); }

public java.security.cert.X509Certificate getCertificate(java.math.BigInteger serial, sun.security.x509.X500Name issuerName) { throw new RuntimeException("Stub!"); }

public java.lang.String toString() { throw new RuntimeException("Stub!"); }

public boolean isOldStyle() { throw new RuntimeException("Stub!"); }
}
