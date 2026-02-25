/*
 * Copyright (C) 2018 The Android Open Source Project
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

package com.android.server.wifi.util;

import static org.junit.Assert.*;

import org.junit.Ignore;
import org.junit.Test;

import java.io.File;
import java.security.DigestException;

/**
 * Unit tests for {@link com.android.server.wifi.util.DataIntegrityChecker}.
 */
public class DataIntegrityCheckerTest {
    private static byte[] sGoodData = {1, 2, 3, 4};
    private static byte[] sBadData = {5, 6, 7, 8};

    /**
     * Verify that updating the integrity token with known data and alias will
     * pass the integrity test. This test ensure the expected outcome for
     * unedited data succeeds.
     *
     * @throws Exception
     */
    @Test
    @Ignore
    public void testIntegrityWithKnownDataAndKnownAlias() throws Exception {
        File integrityFile = File.createTempFile("testIntegrityWithKnownDataAndKnownAlias",
                ".tmp");
        DataIntegrityChecker dataIntegrityChecker = new DataIntegrityChecker(
                integrityFile.getParent());
        dataIntegrityChecker.update(sGoodData);
        assertTrue(dataIntegrityChecker.isOk(sGoodData));
    }

    /**
     * Verify that checking the integrity of unknown data and a known alias
     * will fail the integrity test. This test ensure the expected failure for
     * altered data, in fact, fails.
     *
     *
     * @throws Exception
     */
    @Test
    @Ignore
    public void testIntegrityWithUnknownDataAndKnownAlias() throws Exception {
        File integrityFile = File.createTempFile("testIntegrityWithUnknownDataAndKnownAlias",
                ".tmp");
        DataIntegrityChecker dataIntegrityChecker = new DataIntegrityChecker(
                integrityFile.getParent());
        dataIntegrityChecker.update(sGoodData);
        assertFalse(dataIntegrityChecker.isOk(sBadData));
    }

    /**
     * Verify a corner case where integrity of data that has never been
     * updated passes and adds the token to the keystore.
     *
     * @throws Exception
     */
    @Test(expected = DigestException.class)
    @Ignore
    public void testIntegrityWithoutUpdate() throws Exception {
        File tmpFile = File.createTempFile("testIntegrityWithoutUpdate", ".tmp");

        DataIntegrityChecker dataIntegrityChecker = new DataIntegrityChecker(
                tmpFile.getAbsolutePath());

        // the integrity data is not known, so isOk throws a DigestException
        assertTrue(dataIntegrityChecker.isOk(sGoodData));
    }
}
