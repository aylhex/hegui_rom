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

package libcore.libcore.timezone;

import junit.framework.TestCase;

import libcore.timezone.TzDataSetVersion;
import libcore.timezone.TzDataSetVersion.TzDataSetException;

public class TzDataSetVersionTest extends TestCase {

    private static final int INVALID_VERSION_LOW = -1;
    private static final int VALID_VERSION = 23;
    private static final int INVALID_VERSION_HIGH = 1000;
    private static final String VALID_RULES_VERSION = "2016a";
    private static final String INVALID_RULES_VERSION = "A016a";

    public void testConstructorValidation() throws Exception {
        checkConstructorThrows(
                INVALID_VERSION_LOW, VALID_VERSION, VALID_RULES_VERSION, VALID_VERSION);
        checkConstructorThrows(
                INVALID_VERSION_HIGH, VALID_VERSION, VALID_RULES_VERSION, VALID_VERSION);
        checkConstructorThrows(
                VALID_VERSION, INVALID_VERSION_LOW, VALID_RULES_VERSION, VALID_VERSION);
        checkConstructorThrows(
                VALID_VERSION, INVALID_VERSION_HIGH, VALID_RULES_VERSION, VALID_VERSION);
        checkConstructorThrows(VALID_VERSION, VALID_VERSION, INVALID_RULES_VERSION, VALID_VERSION);
        checkConstructorThrows(VALID_VERSION, VALID_VERSION, VALID_RULES_VERSION,
                INVALID_VERSION_LOW);
        checkConstructorThrows(VALID_VERSION, VALID_VERSION, VALID_RULES_VERSION,
                INVALID_VERSION_HIGH);
    }

    private static void checkConstructorThrows(
            int majorVersion, int minorVersion, String rulesVersion, int revision) {
        try {
            new TzDataSetVersion(majorVersion, minorVersion, rulesVersion, revision);
            fail();
        } catch (TzDataSetException expected) {}
    }

    public void testConstructor() throws Exception {
        TzDataSetVersion distroVersion = new TzDataSetVersion(1, 2, VALID_RULES_VERSION, 3);
        assertEquals(1, distroVersion.formatMajorVersion);
        assertEquals(2, distroVersion.formatMinorVersion);
        assertEquals(VALID_RULES_VERSION, distroVersion.rulesVersion);
        assertEquals(3, distroVersion.revision);
    }

    public void testToFromBytesRoundTrip() throws Exception {
        TzDataSetVersion distroVersion = new TzDataSetVersion(1, 2, VALID_RULES_VERSION, 3);
        assertEquals(distroVersion, TzDataSetVersion.fromBytes(distroVersion.toBytes()));
    }

    public void testIsCompatibleWithThisDevice() throws Exception {
        TzDataSetVersion exactMatch = createTzDataSetVersion(
                TzDataSetVersion.currentFormatMajorVersion(),
                TzDataSetVersion.currentFormatMinorVersion());
        assertTrue(TzDataSetVersion.isCompatibleWithThisDevice(exactMatch));

        TzDataSetVersion newerMajor = createTzDataSetVersion(
                TzDataSetVersion.currentFormatMajorVersion() + 1,
                TzDataSetVersion.currentFormatMinorVersion());
        assertFalse(TzDataSetVersion.isCompatibleWithThisDevice(newerMajor));

        TzDataSetVersion newerMinor = createTzDataSetVersion(
                TzDataSetVersion.currentFormatMajorVersion(),
                TzDataSetVersion.currentFormatMinorVersion() + 1);
        assertTrue(TzDataSetVersion.isCompatibleWithThisDevice(newerMinor));

        // The constant versions should never be below 1. We allow 0 but want to start version
        // numbers at 1 to allow testing of older version logic.
        assertTrue(TzDataSetVersion.currentFormatMajorVersion() >= 1);
        assertTrue(TzDataSetVersion.currentFormatMinorVersion() >= 1);

        TzDataSetVersion olderMajor = createTzDataSetVersion(
                TzDataSetVersion.currentFormatMajorVersion() - 1,
                TzDataSetVersion.currentFormatMinorVersion());
        assertFalse(TzDataSetVersion.isCompatibleWithThisDevice(olderMajor));

        TzDataSetVersion olderMinor = createTzDataSetVersion(
                TzDataSetVersion.currentFormatMajorVersion(),
                TzDataSetVersion.currentFormatMinorVersion() - 1);
        assertFalse(TzDataSetVersion.isCompatibleWithThisDevice(olderMinor));
    }

    private TzDataSetVersion createTzDataSetVersion(int majorFormatVersion, int minorFormatVersion)
            throws TzDataSetException {
        return new TzDataSetVersion(majorFormatVersion, minorFormatVersion, VALID_RULES_VERSION, 3);
    }
}
