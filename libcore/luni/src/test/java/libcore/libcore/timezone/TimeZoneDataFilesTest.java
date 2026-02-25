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

import org.junit.Test;

import libcore.timezone.TimeZoneDataFiles;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertTrue;

public class TimeZoneDataFilesTest {

    private static final String ANDROID_TZDATA_ROOT_ENV = "ANDROID_TZDATA_ROOT";
    private static final String ANDROID_RUNTIME_ROOT_ENV = "ANDROID_RUNTIME_ROOT";

    @Test
    public void expectedEnvironmentVariables() {
        // These environment variables are required to locate data files used by libcore / ICU.
        assertNotNull(System.getenv(ANDROID_TZDATA_ROOT_ENV));
        assertNotNull(System.getenv(ANDROID_RUNTIME_ROOT_ENV));
    }

    @Test
    public void getTimeZoneFilePaths() {
        String[] paths = TimeZoneDataFiles.getTimeZoneFilePaths("foo");
        assertEquals(4, paths.length);

        assertTrue(paths[0].contains("/misc/zoneinfo/current/"));
        assertTrue(paths[0].endsWith("/foo"));

        assertTrue(paths[1].startsWith(System.getenv(ANDROID_TZDATA_ROOT_ENV)));
        assertTrue(paths[1].endsWith("/foo"));

        assertTrue(paths[2].startsWith(System.getenv(ANDROID_RUNTIME_ROOT_ENV)));
        assertTrue(paths[2].endsWith("/foo"));

        assertTrue(paths[3].contains("/usr/share/zoneinfo/"));
        assertTrue(paths[3].endsWith("/foo"));
    }

    // http://b/34867424
    @Test
    public void generateIcuDataPath_includesTimeZoneOverride() {
        String icuDataPath = System.getProperty("android.icu.impl.ICUBinary.dataPath");
        assertEquals(icuDataPath, TimeZoneDataFiles.generateIcuDataPath());

        String[] paths = icuDataPath.split(":");
        assertEquals(3, paths.length);

        String dataDirPath = paths[0];
        assertTrue(dataDirPath + " invalid", dataDirPath.contains("/misc/zoneinfo/current/icu"));

        String tzdataModulePath = paths[1];
        assertTrue(tzdataModulePath + " invalid",
                tzdataModulePath.startsWith(System.getenv(ANDROID_TZDATA_ROOT_ENV)));

        String runtimeModulePath = paths[2];
        assertTrue(runtimeModulePath + " invalid",
                runtimeModulePath.startsWith(System.getenv(ANDROID_RUNTIME_ROOT_ENV)));
        assertTrue(runtimeModulePath + " invalid", runtimeModulePath.contains("/etc/icu"));
    }
}
