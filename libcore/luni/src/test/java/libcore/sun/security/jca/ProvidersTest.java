/*
 * Copyright (C) 2017 The Android Open Source Project
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

package libcore.sun.security.jca;

import com.android.org.bouncycastle.jce.provider.BouncyCastleProvider;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.junit.runners.JUnit4;

import dalvik.system.VMRuntime;

import java.lang.reflect.Method;
import java.security.AlgorithmParameters;
import java.security.GeneralSecurityException;
import java.security.KeyFactory;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.Provider;
import java.security.Security;
import java.security.Signature;
import java.util.ArrayList;
import java.util.List;
import javax.crypto.KeyGenerator;
import javax.crypto.Mac;

import sun.security.jca.Providers;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.fail;

/**
 * Tests that the deprecation of algorithms from the BC provider works as expected.  Requests
 * from an application targeting an API level before the deprecation should receive them,
 * but those targeting an API level after the deprecation should cause an exception.  Tests
 * a representative sample of services and algorithms and various ways of naming them.
 */
@RunWith(JUnit4.class)
public class ProvidersTest {

    /**
     * An object that can be called to call an appropriate getInstance method.  Since
     * each type of object has its own class that the method should be called on,
     * it's either this or reflection, and this seems more straightforward.
     */
    private interface Algorithm {
        Object getInstance() throws GeneralSecurityException;
    }

    // getInstance calls that result in requests to BC
    private static final List<Algorithm> BC_ALGORITHMS = new ArrayList<>();
    // getInstance calls that result in requests to Conscrypt
    private static final List<Algorithm> CONSCRYPT_ALGORITHMS = new ArrayList<>();
    static {
        // A concrete algorithm, provider by name
        BC_ALGORITHMS.add(new Algorithm() {
            @Override
            public Object getInstance() throws GeneralSecurityException {
                return Signature.getInstance("sha224withrsa", "BC");
            }
        });
        // A concrete algorithm, provider by instance
        BC_ALGORITHMS.add(new Algorithm() {
            @Override
            public Object getInstance() throws GeneralSecurityException {
                return KeyFactory.getInstance("EC", Security.getProvider("BC"));
            }
        });
        // An alias for another algorithm, provider by name
        BC_ALGORITHMS.add(new Algorithm() {
            @Override
            public Object getInstance() throws GeneralSecurityException {
                return Signature.getInstance("MD5withRSAEncryption", "BC");
            }
        });
        // An alias for another algorithm, provider by instance
        BC_ALGORITHMS.add(new Algorithm() {
            @Override
            public Object getInstance() throws GeneralSecurityException {
                return KeyGenerator.getInstance("HMAC-MD5", Security.getProvider("BC"));
            }
        });
        // An alias with unusual characters, provider by name
        BC_ALGORITHMS.add(new Algorithm() {
            @Override
            public Object getInstance() throws GeneralSecurityException {
                return Mac.getInstance("Hmac/sha256", "BC");
            }
        });
        // An alias with unusual characters, provider by instance
        BC_ALGORITHMS.add(new Algorithm() {
            @Override
            public Object getInstance() throws GeneralSecurityException {
                return Signature.getInstance("SHA384/rsA", Security.getProvider("BC"));
            }
        });
        // An alias by OID, provider by name
        BC_ALGORITHMS.add(new Algorithm() {
            @Override
            public Object getInstance() throws GeneralSecurityException {
                // OID for SHA-256
                return MessageDigest.getInstance("2.16.840.1.101.3.4.2.1", "BC");
            }
        });
        // An alias by OID, provider by instance
        BC_ALGORITHMS.add(new Algorithm() {
            @Override
            public Object getInstance() throws GeneralSecurityException {
                // OID for AES-128
                return AlgorithmParameters.getInstance("2.16.840.1.101.3.4.1.2",
                        Security.getProvider("BC"));
            }
        });
        // All the same algorithms as for BC, but with no provider, which should produce
        // the Conscrypt implementation
        CONSCRYPT_ALGORITHMS.add(new Algorithm() {
            @Override
            public Object getInstance() throws GeneralSecurityException {
                return Signature.getInstance("sha224withrsa");
            }
        });
        CONSCRYPT_ALGORITHMS.add(new Algorithm() {
            @Override
            public Object getInstance() throws GeneralSecurityException {
                return KeyFactory.getInstance("EC");
            }
        });
        CONSCRYPT_ALGORITHMS.add(new Algorithm() {
            @Override
            public Object getInstance() throws GeneralSecurityException {
                return Signature.getInstance("MD5withRSAEncryption");
            }
        });
        CONSCRYPT_ALGORITHMS.add(new Algorithm() {
            @Override
            public Object getInstance() throws GeneralSecurityException {
                return KeyGenerator.getInstance("HMAC-MD5");
            }
        });
        CONSCRYPT_ALGORITHMS.add(new Algorithm() {
            @Override
            public Object getInstance() throws GeneralSecurityException {
                return Mac.getInstance("Hmac/sha256");
            }
        });
        CONSCRYPT_ALGORITHMS.add(new Algorithm() {
            @Override
            public Object getInstance() throws GeneralSecurityException {
                return Signature.getInstance("SHA384/rsA");
            }
        });
        CONSCRYPT_ALGORITHMS.add(new Algorithm() {
            @Override
            public Object getInstance() throws GeneralSecurityException {
                // OID for SHA-256
                return MessageDigest.getInstance("2.16.840.1.101.3.4.2.1");
            }
        });
        CONSCRYPT_ALGORITHMS.add(new Algorithm() {
            @Override
            public Object getInstance() throws GeneralSecurityException {
                // OID for AES-128
                return AlgorithmParameters.getInstance("2.16.840.1.101.3.4.1.2");
            }
        });
    }

    private static Provider getProvider(Object object) throws Exception {
        // Every JCA object has a getProvider() method
        Method m = object.getClass().getMethod("getProvider");
        return (Provider) m.invoke(object);
    }

    @Test
    public void testBeforeLimit() throws Exception {
        // When we're before the limit of the target API, all calls should succeed
        try {
            Providers.setMaximumAllowableApiLevelForBcDeprecation(
                    VMRuntime.getRuntime().getTargetSdkVersion() + 1);
            for (Algorithm a : BC_ALGORITHMS) {
                Object result = a.getInstance();
                assertEquals("BC", getProvider(result).getName());
            }
            for (Algorithm a : CONSCRYPT_ALGORITHMS) {
                Object result = a.getInstance();
                assertEquals("AndroidOpenSSL", getProvider(result).getName());
            }
        } finally {
            Providers.setMaximumAllowableApiLevelForBcDeprecation(
                    Providers.DEFAULT_MAXIMUM_ALLOWABLE_TARGET_API_LEVEL_FOR_BC_DEPRECATION);
        }
    }

    @Test
    public void testAtLimit() throws Exception {
        // When we're at the limit of the target API, all calls should still succeed
        try {
            Providers.setMaximumAllowableApiLevelForBcDeprecation(
                    VMRuntime.getRuntime().getTargetSdkVersion());
            for (Algorithm a : BC_ALGORITHMS) {
                Object result = a.getInstance();
                assertEquals("BC", getProvider(result).getName());
            }
            for (Algorithm a : CONSCRYPT_ALGORITHMS) {
                Object result = a.getInstance();
                assertEquals("AndroidOpenSSL", getProvider(result).getName());
            }
        } finally {
            Providers.setMaximumAllowableApiLevelForBcDeprecation(
                    Providers.DEFAULT_MAXIMUM_ALLOWABLE_TARGET_API_LEVEL_FOR_BC_DEPRECATION);
        }
    }

    @Test
    public void testPastLimit() throws Exception {
        // When we're beyond the limit of the target API, the Conscrypt calls should succeed
        // but the BC calls should throw NoSuchAlgorithmException
        try {
            Providers.setMaximumAllowableApiLevelForBcDeprecation(
                    VMRuntime.getRuntime().getTargetSdkVersion() - 1);
            for (Algorithm a : BC_ALGORITHMS) {
                try {
                    a.getInstance();
                    fail("getInstance should have thrown");
                } catch (NoSuchAlgorithmException expected) {
                }
            }
            for (Algorithm a : CONSCRYPT_ALGORITHMS) {
                Object result = a.getInstance();
                assertEquals("AndroidOpenSSL", getProvider(result).getName());
            }
        } finally {
            Providers.setMaximumAllowableApiLevelForBcDeprecation(
                    Providers.DEFAULT_MAXIMUM_ALLOWABLE_TARGET_API_LEVEL_FOR_BC_DEPRECATION);
        }
    }

    @Test
    public void testCustomProvider() throws Exception {
        // When we install our own separate instance of Bouncy Castle, the system should
        // respect that and allow us to use its implementation.
        Provider originalBouncyCastle = null;
        int originalBouncyCastleIndex = -1;
        for (int i = 0; i < Security.getProviders().length; i++) {
            if (Security.getProviders()[i].getName().equals("BC")) {
                originalBouncyCastle = Security.getProviders()[i];
                originalBouncyCastleIndex = i;
                break;
            }
        }
        assertNotNull(originalBouncyCastle);
        Provider newBouncyCastle = new BouncyCastleProvider();
        assertEquals("BC", newBouncyCastle.getName());
        try {
            // Remove the existing BC provider and replace it with a different one
            Security.removeProvider("BC");
            Security.insertProviderAt(newBouncyCastle, originalBouncyCastleIndex);
            // Set the target API limit such that the BC algorithms are disallowed
            Providers.setMaximumAllowableApiLevelForBcDeprecation(
                    VMRuntime.getRuntime().getTargetSdkVersion() - 1);
            for (Algorithm a : BC_ALGORITHMS) {
                Object result = a.getInstance();
                assertEquals("BC", getProvider(result).getName());
            }
            for (Algorithm a : CONSCRYPT_ALGORITHMS) {
                Object result = a.getInstance();
                assertEquals("AndroidOpenSSL", getProvider(result).getName());
            }
        } finally {
            Providers.setMaximumAllowableApiLevelForBcDeprecation(
                    Providers.DEFAULT_MAXIMUM_ALLOWABLE_TARGET_API_LEVEL_FOR_BC_DEPRECATION);
            Security.removeProvider("BC");
            Security.insertProviderAt(originalBouncyCastle, originalBouncyCastleIndex);
        }
    }
}