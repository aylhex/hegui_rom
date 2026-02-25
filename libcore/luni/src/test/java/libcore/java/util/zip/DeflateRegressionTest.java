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

package libcore.java.util.zip;

import com.google.archivepatcher.shared.DefaultDeflateCompatibilityWindow;

import org.junit.Test;

import static org.junit.Assert.assertTrue;

/**
 * A regression test for Deflate and the underlying native libraries. If any of these tests fail
 * it suggests that tools such as Google Play Store that rely on deterministic binary output from
 * Deflate; those tools may behave inefficiently if the output changes.
 */
public class DeflateRegressionTest {

    /*
     * If this test fails then it implies a change that could regress Android user performance.
     * Please check that the platform version of Deflate is still used by affected tools and notify
     * them. See also http://b/27637914.
     */
    @Test
    public void deterministicOutput() throws Exception {
        assertTrue(new DefaultDeflateCompatibilityWindow().isCompatible());
    }
}
