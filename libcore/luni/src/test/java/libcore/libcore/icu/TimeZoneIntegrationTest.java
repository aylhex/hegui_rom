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

package libcore.libcore.icu;

import org.junit.Test;

import android.icu.text.TimeZoneNames;
import android.icu.util.VersionInfo;
import android.system.Os;

import java.io.File;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Date;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.concurrent.BrokenBarrierException;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Function;
import java.util.stream.Collectors;

import libcore.icu.ICU;
import libcore.timezone.TimeZoneDataFiles;
import libcore.timezone.TimeZoneFinder;
import libcore.timezone.TzDataSetVersion;
import libcore.timezone.ZoneInfoDB;
import libcore.util.CoreLibraryDebug;
import libcore.util.DebugInfo;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;
import static org.junit.Assert.fail;

/**
 * Tests that compare ICU and libcore time zone behavior and similar cross-cutting concerns.
 */
public class TimeZoneIntegrationTest {

    // http://b/28949992
    @Test
    public void testJavaSetDefaultAppliesToIcuTimezone() {
        java.util.TimeZone origTz = java.util.TimeZone.getDefault();
        try {
            android.icu.util.TimeZone origIcuTz = android.icu.util.TimeZone.getDefault();
            assertEquals(origTz.getID(), origIcuTz.getID());

            java.util.TimeZone tz = java.util.TimeZone.getTimeZone("GMT-05:00");
            java.util.TimeZone.setDefault(tz);
            android.icu.util.TimeZone icuTz = android.icu.util.TimeZone.getDefault();
            assertEquals(tz.getID(), icuTz.getID());
        } finally {
            java.util.TimeZone.setDefault(origTz);
        }
    }

    // http://b/30937209
    @Test
    public void testSetDefaultDeadlock() throws InterruptedException, BrokenBarrierException {
        // Since this tests a deadlock, the test has two fundamental problems:
        // - it is probabilistic: it's not guaranteed to fail if the problem exists
        // - if it fails, it will effectively hang the current runtime, as no other thread will
        //   be able to call TimeZone.getDefault()/setDefault() successfully any more.

        // 10 was too low to be reliable, 100 failed more than half the time (on a bullhead).
        final int iterations = 100;
        java.util.TimeZone otherTimeZone = java.util.TimeZone.getTimeZone("Europe/London");
        AtomicInteger setterCount = new AtomicInteger();
        CyclicBarrier startBarrier = new CyclicBarrier(2);
        Thread setter = new Thread(() -> {
            waitFor(startBarrier);
            for (int i = 0; i < iterations; i++) {
                java.util.TimeZone.setDefault(otherTimeZone);
                java.util.TimeZone.setDefault(null);
                setterCount.set(i+1);
            }
        });
        setter.setName("testSetDefaultDeadlock setter");

        AtomicInteger getterCount = new AtomicInteger();
        Thread getter = new Thread(() -> {
            waitFor(startBarrier);
            for (int i = 0; i < iterations; i++) {
                android.icu.util.TimeZone.getDefault();
                getterCount.set(i+1);
            }
        });
        getter.setName("testSetDefaultDeadlock getter");

        setter.start();
        getter.start();

        // 2 seconds is plenty: If successful, we usually complete much faster.
        setter.join(1000);
        getter.join(1000);
        if (setter.isAlive() || getter.isAlive()) {
            fail("Threads are still alive. Getter iteration count: " + getterCount.get()
                    + ", setter iteration count: " + setterCount.get());
        }
        // Guard against unexpected uncaught exceptions.
        assertEquals("Setter iterations", iterations, setterCount.get());
        assertEquals("Getter iterations", iterations, getterCount.get());
    }

    // http://b/30979219
    @Test
    public void testSetDefaultRace() throws InterruptedException {
        // Since this tests a race condition, the test is probabilistic: it's not guaranteed to
        // fail if the problem exists

        // These iterations are significantly faster than the ones in #testSetDefaultDeadlock
        final int iterations = 10000;
        List<Throwable> exceptions = Collections.synchronizedList(new ArrayList<>());
        Thread.UncaughtExceptionHandler handler = (t, e) -> exceptions.add(e);

        CyclicBarrier startBarrier = new CyclicBarrier(2);
        Thread clearer = new Thread(() -> {
            waitFor(startBarrier);
            for (int i = 0; i < iterations; i++) {
                // This is not public API but can effectively be invoked via
                // java.util.TimeZone.setDefault. Call it directly to reduce the amount of code
                // involved in this test.
                android.icu.util.TimeZone.setICUDefault(null);
            }
        });
        clearer.setName("testSetDefaultRace clearer");
        clearer.setUncaughtExceptionHandler(handler);

        Thread getter = new Thread(() -> {
            waitFor(startBarrier);
            for (int i = 0; i < iterations; i++) {
                android.icu.util.TimeZone.getDefault();
            }
        });
        getter.setName("testSetDefaultRace getter");
        getter.setUncaughtExceptionHandler(handler);

        clearer.start();
        getter.start();

        // 20 seconds is plenty: If successful, we usually complete much faster.
        clearer.join(10000);
        getter.join(10000);

        if (!exceptions.isEmpty()) {
            Throwable firstException = exceptions.get(0);
            firstException.printStackTrace();
            fail("Threads did not succeed successfully: " + firstException);
        }
        assertFalse("clearer thread is still alive", clearer.isAlive());
        assertFalse("getter thread is still alive", getter.isAlive());
    }

    private static void waitFor(CyclicBarrier barrier) {
        try {
            barrier.await();
        } catch (InterruptedException | BrokenBarrierException e) {
            throw new RuntimeException(e);
        }
    }

    /**
     * Confirms that ICU agrees with the rest of libcore about the version of the TZ data in use.
     */
    @Test
    public void testTimeZoneDataVersion() {
        String icu4cTzVersion = ICU.getTZDataVersion();

        String zoneInfoTzVersion = ZoneInfoDB.getInstance().getVersion();
        assertEquals(icu4cTzVersion, zoneInfoTzVersion);

        String icu4jTzVersion = android.icu.util.TimeZone.getTZDataVersion();
        assertEquals(icu4jTzVersion, zoneInfoTzVersion);

        String tzLookupTzVersion = TimeZoneFinder.getInstance().getIanaVersion();
        assertEquals(icu4jTzVersion, tzLookupTzVersion);
    }

    /**
     * Asserts that the time zone format major / minor versions meets expectations.
     *
     * <p>If a set of time zone files is to be compatible with a device then the format of the files
     * must meet the Android team's expectations. This is a sanity check to ensure that devices
     * running the test (e.g. under CTS) have not modified the TzDataSetVersion major / minor
     * versions for some reason: if they have it would render updated time zone files sent to the
     * device incompatible.
     */
    @Test
    public void testTimeZoneFormatVersion() {
        // The code below compares the final static int constant values (inlined at test compile
        // time) with the version reported at runtime. This saves us hardcoding the numbers in two
        // places.
        assertEquals(TzDataSetVersion.CURRENT_FORMAT_MAJOR_VERSION,
                TzDataSetVersion.currentFormatMajorVersion());
        assertEquals(TzDataSetVersion.CURRENT_FORMAT_MINOR_VERSION,
                TzDataSetVersion.currentFormatMinorVersion());
    }

    /**
     * Asserts that all expected sets of time zone files meet format expectations.
     *
     * <p>This uses the device's knowledge of the format version it expects and the
     * {@link TzDataSetVersion} files that accompany the known time zone data files.
     *
     * <p>This is a sanity check to ensure that there's no way of installing incompatible data
     * on a device. It assumes that {@link TzDataSetVersion} is updated as it should be when changes
     * are made that might affect time zone code / time zone data compatibility.
     */
    @Test
    public void testTzDataSetVersions() throws Exception {
        String moduleTzVersionFile = "tz/" + TzDataSetVersion.DEFAULT_FILE_NAME;

        String timeZoneModuleVersionFile =
                TimeZoneDataFiles.getTimeZoneModuleFile(moduleTzVersionFile);
        // We currently treat the time zone APEX as optional in code. Its is also not present on ART
        // host environments.
        if (fileExists(timeZoneModuleVersionFile)) {
            assertTzDataSetVersionIsCompatible(timeZoneModuleVersionFile);
        }

        String runtimeModuleVersionFile =
                TimeZoneDataFiles.getRuntimeModuleFile(moduleTzVersionFile);
        assertTzDataSetVersionIsCompatible(runtimeModuleVersionFile);

        // Check getRuntimeModuleTzVersionFile() is doing the right thing.
        // getRuntimeModuleTzVersionFile() should go away when its one user, RulesManagerService,
        // is removed from the platform code. http://b/123398797
        assertEquals(TimeZoneDataFiles.getRuntimeModuleTzVersionFile(), runtimeModuleVersionFile);

        // TODO: Remove this once the /system copy of time zone files have gone away. See also
        // testTimeZoneDebugInfo().
        assertTzDataSetVersionIsCompatible(
                TimeZoneDataFiles.getSystemTimeZoneFile(TzDataSetVersion.DEFAULT_FILE_NAME));
    }

    private static void assertTzDataSetVersionIsCompatible(String versionFile) throws Exception {
        TzDataSetVersion actualVersion =
                TzDataSetVersion.readFromFile(new File(versionFile));
        assertEquals(
                TzDataSetVersion.currentFormatMajorVersion(),
                actualVersion.formatMajorVersion);
        int minDeviceMinorVersion = TzDataSetVersion.currentFormatMinorVersion();
        assertTrue(actualVersion.formatMinorVersion >= minDeviceMinorVersion);
    }

    /**
     * A test for confirming debug information matches file system state on device.
     * It can also be used to confirm that device and host environments satisfy file system
     * expectations.
     */
    @Test
    public void testTimeZoneDebugInfo() throws Exception {
        DebugInfo debugInfo = CoreLibraryDebug.getDebugInfo();

        // Devices are expected to have a time zone module which overrides or extends the data in
        // the runtime module depending on the file. It's not actually mandatory for all Android
        // devices right now although it may be required for some subset of Android devices. It
        // isn't present on host ART.
        String tzModuleStatus = getDebugStringValue(debugInfo,
                "core_library.timezone.source.tzdata_module_status");
        String apexRootDir = TimeZoneDataFiles.getTimeZoneModuleFile("");
        List<String> dataModuleFiles =
                createModuleTzFileNames(TimeZoneDataFiles::getTimeZoneModuleFile);
        String icuOverlayFile = TimeZoneDataFiles.getTimeZoneModuleFile("icu/icu_tzdata.dat");
        if (fileExists(apexRootDir)) {
            assertEquals("OK", tzModuleStatus);
            dataModuleFiles.forEach(TimeZoneIntegrationTest::assertFileExists);
            assertFileExists(icuOverlayFile);
        } else {
            assertEquals("NOT_FOUND", tzModuleStatus);
            dataModuleFiles.forEach(TimeZoneIntegrationTest::assertFileDoesNotExist);
            assertFileDoesNotExist(icuOverlayFile);
        }

        // Every device should have a runtime module copy of time zone data since we expect every
        // device to have a runtime module. This is the base copy of time zone data that can be
        // updated when we update the runtime module. Host ART should match device.
        assertEquals("OK", getDebugStringValue(debugInfo,
                "core_library.timezone.source.runtime_module_status"));
        assertFileExists(TimeZoneDataFiles.getRuntimeModuleFile(""));
        List<String> runtimeModuleFiles =
                createModuleTzFileNames(TimeZoneDataFiles::getRuntimeModuleFile);
        runtimeModuleFiles.forEach(TimeZoneIntegrationTest::assertFileExists);

        String icuDatFileName = "icudt" + VersionInfo.ICU_VERSION.getMajor() + "l.dat";
        String runtimeModuleIcuData =
                TimeZoneDataFiles.getRuntimeModuleFile("icu/" + icuDatFileName);
        assertFileExists(runtimeModuleIcuData);

        // Devices currently have a subset of the time zone files in /system. These are going away
        // but we test them while they exist. Host ART should match device.
        assertEquals("OK", getDebugStringValue(debugInfo,
                "core_library.timezone.source.system_status"));
        assertFileExists(
                TimeZoneDataFiles.getSystemTimeZoneFile(TzDataSetVersion.DEFAULT_FILE_NAME));
        assertFileExists(TimeZoneDataFiles.getSystemTimeZoneFile("tzdata"));
        // The following files once existed in /system but have been removed as part of APEX work.
        assertFileDoesNotExist(TimeZoneDataFiles.getSystemTimeZoneFile("tzlookup.xml"));

        // It's hard to assert much about this file as there is a symlink in /system on device for
        // app compatibility (b/122985829) but it doesn't exist in host environments. If the file
        // exists we can say it should resolve (realpath) to the same file as the runtime module.
        String systemIcuData = TimeZoneDataFiles.getSystemIcuFile(icuDatFileName);
        if (new File(systemIcuData).exists()) {
            assertEquals(Os.realpath(runtimeModuleIcuData), Os.realpath(systemIcuData));
        }
    }

    private static List<String> createModuleTzFileNames(
            Function<String, String> pathCreationFunction) {
        List<String> relativePaths = Arrays.asList(
                "tz/" + TzDataSetVersion.DEFAULT_FILE_NAME,
                "tz/tzdata",
                "tz/tzlookup.xml");
        return relativePaths.stream().map(pathCreationFunction).collect(Collectors.toList());
    }

    private static boolean fileExists(String fileName) {
        return new File(fileName).exists();
    }

    private static void assertFileDoesNotExist(String fileName) {
        assertFalse(fileName + " must not exist", fileExists(fileName));
    }

    private static void assertFileExists(String fileName) {
        assertTrue(fileName + " must exist", fileExists(fileName));
    }

    private String getDebugStringValue(DebugInfo debugInfo, String key) {
        return debugInfo.getDebugEntry(key).getStringValue();
    }

    /**
     * Confirms that ICU can recognize all the time zone IDs used by the ZoneInfoDB data.
     * ICU's IDs may be a superset.
     */
    @Test
    public void testTimeZoneIdLookup() {
        String[] zoneInfoDbAvailableIds = ZoneInfoDB.getInstance().getAvailableIDs();

        // ICU has a known set of IDs. We want ANY because we don't want to filter to ICU's
        // canonical IDs only.
        Set<String> icuAvailableIds = android.icu.util.TimeZone.getAvailableIDs(
                android.icu.util.TimeZone.SystemTimeZoneType.ANY, null /* region */,
                null /* rawOffset */);

        List<String> nonIcuAvailableIds = new ArrayList<>();
        List<String> creationFailureIds = new ArrayList<>();
        List<String> noCanonicalLookupIds = new ArrayList<>();
        List<String> nonSystemIds = new ArrayList<>();
        for (String zoneInfoDbId : zoneInfoDbAvailableIds) {
            if (!icuAvailableIds.contains(zoneInfoDbId)) {
                nonIcuAvailableIds.add(zoneInfoDbId);
            }

            boolean[] isSystemId = new boolean[1];
            String canonicalId = android.icu.util.TimeZone.getCanonicalID(zoneInfoDbId, isSystemId);
            if (canonicalId == null) {
                noCanonicalLookupIds.add(zoneInfoDbId);
            }
            if (!isSystemId[0]) {
                nonSystemIds.add(zoneInfoDbId);
            }

            android.icu.util.TimeZone icuTimeZone =
                    android.icu.util.TimeZone.getTimeZone(zoneInfoDbId);
            if (icuTimeZone.getID().equals(android.icu.util.TimeZone.UNKNOWN_ZONE_ID)) {
                creationFailureIds.add(zoneInfoDbId);
            }
        }
        assertTrue("Non-ICU available IDs: " + nonIcuAvailableIds
                        + ", creation failed IDs: " + creationFailureIds
                        + ", non-system IDs: " + nonSystemIds
                        + ", ids without canonical IDs: " + noCanonicalLookupIds,
                nonIcuAvailableIds.isEmpty()
                        && creationFailureIds.isEmpty()
                        && nonSystemIds.isEmpty()
                        && noCanonicalLookupIds.isEmpty());
    }

    // http://b/30527513
    @Test
    public void testDisplayNamesWithScript() throws Exception {
        Locale latinLocale = Locale.forLanguageTag("sr-Latn-RS");
        Locale cyrillicLocale = Locale.forLanguageTag("sr-Cyrl-RS");
        Locale noScriptLocale = Locale.forLanguageTag("sr-RS");
        java.util.TimeZone tz = java.util.TimeZone.getTimeZone("Europe/London");

        final String latinName = "Srednje vreme po Griniču";
        final String cyrillicName = "Средње време по Гриничу";

        // Check java.util.TimeZone
        assertEquals(latinName, tz.getDisplayName(latinLocale));
        assertEquals(cyrillicName, tz.getDisplayName(cyrillicLocale));
        assertEquals(cyrillicName, tz.getDisplayName(noScriptLocale));

        // Check ICU TimeZoneNames
        // The one-argument getDisplayName() override uses LONG_GENERIC style which is different
        // from what java.util.TimeZone uses. Force the LONG style to get equivalent results.
        final int style = android.icu.util.TimeZone.LONG;
        android.icu.util.TimeZone utz = android.icu.util.TimeZone.getTimeZone(tz.getID());
        assertEquals(latinName, utz.getDisplayName(false, style, latinLocale));
        assertEquals(cyrillicName, utz.getDisplayName(false, style, cyrillicLocale));
        assertEquals(cyrillicName, utz.getDisplayName(false, style, noScriptLocale));
    }

    /**
     * This test is to catch issues with the rules update process that could let the
     * "negative DST" scheme enter the Android data set for either java.util.TimeZone or
     * android.icu.util.TimeZone.
     */
    @Test
    public void testDstMeansSummer() {
        // Ireland was the original example that caused the default IANA upstream tzdata to contain
        // a zone where DST is in the Winter (since tzdata 2018e, though it was tried in 2018a
        // first). This change was made to historical and future transitions.
        //
        // The upstream reasoning went like this: "Irish *Standard* Time" is summer, so the other
        // time must be the DST. So, DST is considered to be in the winter and the associated DST
        // adjustment is negative from the standard time. In the old scheme "Irish Standard Time" /
        // summer was just modeled as the DST in common with all other global time zones.
        //
        // Unfortunately, various users of formatting APIs assume standard and DST times are
        // consistent and (effectively) that "DST" means "summer". We likely cannot adopt the
        // concept of a winter DST without risking app compat issues.
        //
        // For example, getDisplayName(boolean daylight) has always returned the winter time for
        // false, and the summer time for true. If we change this then it should be changed on a
        // major release boundary, with improved APIs (e.g. a version of getDisplayName() that takes
        // a millis), existing API behavior made dependent on target API version, and after fixing
        // any platform code that makes incorrect assumptions about DST meaning "1 hour forward".

        final String timeZoneId = "Europe/Dublin";
        final Locale locale = Locale.UK;
        // 26 Oct 2015 01:00:00 GMT - one day after the start of "Greenwich Mean Time" in
        // Europe/Dublin in 2015. An arbitrary historical example of winter in Ireland.
        final long winterTimeMillis = 1445821200000L;
        final String winterTimeName = "Greenwich Mean Time";
        final int winterOffsetRawMillis = 0;
        final int winterOffsetDstMillis = 0;

        // 30 Mar 2015 01:00:00 GMT - one day after the start of "Irish Standard Time" in
        // Europe/Dublin in 2015. An arbitrary historical example of summer in Ireland.
        final long summerTimeMillis = 1427677200000L;
        final String summerTimeName = "Irish Standard Time";
        final int summerOffsetRawMillis = 0;
        final int summerOffsetDstMillis = (int) TimeUnit.HOURS.toMillis(1);

        // There is no common interface between java.util.TimeZone and android.icu.util.TimeZone
        // so the tests are for each are effectively duplicated.

        // java.util.TimeZone
        {
            java.util.TimeZone timeZone = java.util.TimeZone.getTimeZone(timeZoneId);
            assertTrue(timeZone.useDaylightTime());

            assertFalse(timeZone.inDaylightTime(new Date(winterTimeMillis)));
            assertTrue(timeZone.inDaylightTime(new Date(summerTimeMillis)));

            assertEquals(winterOffsetRawMillis + winterOffsetDstMillis,
                    timeZone.getOffset(winterTimeMillis));
            assertEquals(summerOffsetRawMillis + summerOffsetDstMillis,
                    timeZone.getOffset(summerTimeMillis));
            assertEquals(winterTimeName,
                    timeZone.getDisplayName(false /* daylight */, java.util.TimeZone.LONG,
                            locale));
            assertEquals(summerTimeName,
                    timeZone.getDisplayName(true /* daylight */, java.util.TimeZone.LONG,
                            locale));
        }

        // android.icu.util.TimeZone
        {
            android.icu.util.TimeZone timeZone = android.icu.util.TimeZone.getTimeZone(timeZoneId);
            assertTrue(timeZone.useDaylightTime());

            assertFalse(timeZone.inDaylightTime(new Date(winterTimeMillis)));
            assertTrue(timeZone.inDaylightTime(new Date(summerTimeMillis)));

            assertEquals(winterOffsetRawMillis + winterOffsetDstMillis,
                    timeZone.getOffset(winterTimeMillis));
            assertEquals(summerOffsetRawMillis + summerOffsetDstMillis,
                    timeZone.getOffset(summerTimeMillis));

            // These methods show the trouble we'd have if callers were to take the output from
            // inDaylightTime() and pass it to getDisplayName().
            assertEquals(winterTimeName,
                    timeZone.getDisplayName(false /* daylight */, android.icu.util.TimeZone.LONG,
                            locale));
            assertEquals(summerTimeName,
                    timeZone.getDisplayName(true /* daylight */, android.icu.util.TimeZone.LONG,
                            locale));

            // APIs not identical to java.util.TimeZone tested below.
            int[] offsets = new int[2];
            timeZone.getOffset(winterTimeMillis, false /* local */, offsets);
            assertEquals(winterOffsetRawMillis, offsets[0]);
            assertEquals(winterOffsetDstMillis, offsets[1]);

            timeZone.getOffset(summerTimeMillis, false /* local */, offsets);
            assertEquals(summerOffsetRawMillis, offsets[0]);
            assertEquals(summerOffsetDstMillis, offsets[1]);
        }

        // icu TimeZoneNames
        TimeZoneNames timeZoneNames = TimeZoneNames.getInstance(locale);
        // getDisplayName: date = winterTimeMillis
        assertEquals(winterTimeName, timeZoneNames.getDisplayName(
                timeZoneId, TimeZoneNames.NameType.LONG_STANDARD, winterTimeMillis));
        assertEquals(summerTimeName, timeZoneNames.getDisplayName(
                timeZoneId, TimeZoneNames.NameType.LONG_DAYLIGHT, winterTimeMillis));
        // getDisplayName: date = summerTimeMillis
        assertEquals(winterTimeName, timeZoneNames.getDisplayName(
                timeZoneId, TimeZoneNames.NameType.LONG_STANDARD, summerTimeMillis));
        assertEquals(summerTimeName, timeZoneNames.getDisplayName(
                timeZoneId, TimeZoneNames.NameType.LONG_DAYLIGHT, summerTimeMillis));
    }
}
