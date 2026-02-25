package libcore.java.security.cert;

import java.io.IOException;
import java.io.OutputStream;
import java.net.URI;
import java.security.KeyStore.PrivateKeyEntry;
import java.security.cert.CertPathBuilder;
import java.security.cert.CertPathChecker;
import java.security.cert.Extension;
import java.security.cert.PKIXRevocationChecker;
import java.security.cert.PKIXRevocationChecker.Option;
import java.security.cert.X509Certificate;
import java.util.Arrays;
import java.util.Collections;
import java.util.Map;

import junit.framework.TestCase;
import libcore.java.security.TestKeyStore;

import dalvik.system.VMRuntime;
import sun.security.jca.Providers;

public class PKIXRevocationCheckerTest extends TestCase {
    PKIXRevocationChecker checker;

    PrivateKeyEntry entity;

    PrivateKeyEntry issuer;

    @Override
    protected void setUp() throws Exception {
        super.setUp();

        // Allow access to deprecated BC algorithms in this test, so we can ensure they
        // continue to work
        Providers.setMaximumAllowableApiLevelForBcDeprecation(
                VMRuntime.getRuntime().getTargetSdkVersion());

        CertPathBuilder cpb = CertPathBuilder.getInstance("PKIX");
        CertPathChecker rc = cpb.getRevocationChecker();
        assertNotNull(rc);
        assertTrue(rc instanceof PKIXRevocationChecker);
        checker = (PKIXRevocationChecker) rc;

        TestKeyStore server = TestKeyStore.getServer();
        TestKeyStore intermediate = TestKeyStore.getIntermediateCa();

        entity = server.getPrivateKey("RSA", "RSA");
        issuer = intermediate.getPrivateKey("RSA", "RSA");
    }

    @Override
    public void tearDown() throws Exception {
        Providers.setMaximumAllowableApiLevelForBcDeprecation(
                Providers.DEFAULT_MAXIMUM_ALLOWABLE_TARGET_API_LEVEL_FOR_BC_DEPRECATION);
        super.tearDown();
    }

    public void test_Initializes() throws Exception {
        assertEquals(0, checker.getOcspResponses().size());
        assertEquals(0, checker.getOcspExtensions().size());
        assertEquals(0, checker.getOptions().size());
        assertEquals(0, checker.getSoftFailExceptions().size());
        assertNull(checker.getSupportedExtensions());
        assertNull(checker.getOcspResponderCert());
        assertNull(checker.getOcspResponder());
    }

    public void test_CanSetOCSPResponse() throws Exception {
        byte[] goodOCSPResponse = TestKeyStore.getOCSPResponseForGood(entity, issuer);

        Map<X509Certificate, byte[]> ocspResponses = Collections
                .singletonMap((X509Certificate) entity.getCertificate(), goodOCSPResponse);
        checker.setOcspResponses(ocspResponses);

        Map<X509Certificate, byte[]> returnedResponses = checker.getOcspResponses();
        assertEquals(1, returnedResponses.size());
        byte[] returnedResponse = returnedResponses.get(entity.getCertificate());
        assertNotNull(returnedResponse);
        assertEquals(Arrays.toString(goodOCSPResponse), Arrays.toString(returnedResponse));
    }

    public void test_getOcspResponder() throws Exception {
        URI url = new URI("http://localhost/");
        checker.setOcspResponder(url);
        assertEquals(url, checker.getOcspResponder());
    }

    public void test_getOcspResponderCert() throws Exception {
        checker.setOcspResponderCert((X509Certificate) issuer.getCertificate());
        assertEquals((X509Certificate) issuer.getCertificate(), checker.getOcspResponderCert());
    }

    public void test_getOptions() throws Exception {
        checker.setOptions(Collections.singleton(Option.SOFT_FAIL));
        assertEquals(Collections.singleton(Option.SOFT_FAIL), checker.getOptions());
    }

    public void test_getOcspExtensions() throws Exception {
        checker.setOcspExtensions(Collections.singletonList(new Extension() {
            @Override
            public boolean isCritical() {
                throw new UnsupportedOperationException();
            }

            @Override
            public byte[] getValue() {
                throw new UnsupportedOperationException();
            }

            @Override
            public String getId() {
                return "TestExtension";
            }

            @Override
            public void encode(OutputStream out) throws IOException {
                throw new UnsupportedOperationException();
            }
        }));
        assertEquals(1, checker.getOcspExtensions().size());
        assertEquals("TestExtension", checker.getOcspExtensions().get(0).getId());
    }
}
