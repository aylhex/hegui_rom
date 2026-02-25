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

import org.junit.After;
import org.junit.Before;
import org.junit.Test;

import android.icu.util.TimeZone;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.Arrays;
import java.util.Collection;
import java.util.List;
import java.util.stream.Collectors;
import libcore.timezone.CountryTimeZones;
import libcore.timezone.CountryTimeZones.TimeZoneMapping;
import libcore.timezone.CountryZonesFinder;
import libcore.timezone.TimeZoneFinder;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.fail;

public class TimeZoneFinderTest {

    private static final int HOUR_MILLIS = 60 * 60 * 1000;

    // Zones used in the tests. NEW_YORK_TZ and LONDON_TZ chosen because they never overlap but both
    // have DST.
    private static final TimeZone NEW_YORK_TZ = TimeZone.getTimeZone("America/New_York");
    private static final TimeZone LONDON_TZ = TimeZone.getTimeZone("Europe/London");
    // A zone that matches LONDON_TZ for WHEN_NO_DST. It does not have DST so differs for WHEN_DST.
    private static final TimeZone REYKJAVIK_TZ = TimeZone.getTimeZone("Atlantic/Reykjavik");
    // Another zone that matches LONDON_TZ for WHEN_NO_DST. It does not have DST so differs for
    // WHEN_DST.
    private static final TimeZone UTC_TZ = TimeZone.getTimeZone("Etc/UTC");

    // 22nd July 2017, 13:14:15 UTC (DST time in all the timezones used in these tests that observe
    // DST).
    private static final long WHEN_DST = 1500729255000L;
    // 22nd January 2018, 13:14:15 UTC (non-DST time in all timezones used in these tests).
    private static final long WHEN_NO_DST = 1516626855000L;

    private static final int LONDON_DST_OFFSET_MILLIS = HOUR_MILLIS;
    private static final int LONDON_NO_DST_OFFSET_MILLIS = 0;

    private static final int NEW_YORK_DST_OFFSET_MILLIS = -4 * HOUR_MILLIS;
    private static final int NEW_YORK_NO_DST_OFFSET_MILLIS = -5 * HOUR_MILLIS;

    private Path testDir;

    @Before
    public void setUp() throws Exception {
        testDir = Files.createTempDirectory("TimeZoneFinderTest");
    }

    @After
    public void tearDown() throws Exception {
        // Delete the testDir and all contents.
        Files.walkFileTree(testDir, new SimpleFileVisitor<Path>() {
            @Override
            public FileVisitResult visitFile(Path file, BasicFileAttributes attrs)
                    throws IOException {
                Files.delete(file);
                return FileVisitResult.CONTINUE;
            }

            @Override
            public FileVisitResult postVisitDirectory(Path dir, IOException exc)
                    throws IOException {
                Files.delete(dir);
                return FileVisitResult.CONTINUE;
            }
        });
    }

    @Test
    public void createInstanceWithFallback() throws Exception {
        String validXml1 = "<timezones ianaversion=\"2017c\">\n"
                + "  <countryzones>\n"
                + "    <country code=\"gb\" default=\"Europe/London\" everutc=\"y\">\n"
                + "      <id>Europe/London</id>\n"
                + "    </country>\n"
                + "  </countryzones>\n"
                + "</timezones>\n";
        CountryTimeZones expectedCountryTimeZones1 = CountryTimeZones.createValidated(
                "gb", "Europe/London", true /* everUsesUtc */, timeZoneMappings("Europe/London"),
                "test");

        String validXml2 = "<timezones ianaversion=\"2017b\">\n"
                + "  <countryzones>\n"
                + "    <country code=\"gb\" default=\"Europe/Paris\" everutc=\"n\">\n"
                + "      <id>Europe/Paris</id>\n"
                + "    </country>\n"
                + "  </countryzones>\n"
                + "</timezones>\n";
        CountryTimeZones expectedCountryTimeZones2 = CountryTimeZones.createValidated(
                "gb", "Europe/Paris", false /* everUsesUtc */, timeZoneMappings("Europe/Paris"),
                "test");

        String invalidXml = "<foo></foo>\n";
        checkValidateThrowsParserException(invalidXml);

        String validFile1 = createFile(validXml1);
        String validFile2 = createFile(validXml2);
        String invalidFile = createFile(invalidXml);
        String missingFile = createMissingFile();

        TimeZoneFinder file1ThenFile2 =
                TimeZoneFinder.createInstanceWithFallback(validFile1, validFile2);
        assertEquals("2017c", file1ThenFile2.getIanaVersion());
        assertEquals(expectedCountryTimeZones1, file1ThenFile2.lookupCountryTimeZones("gb"));

        TimeZoneFinder missingFileThenFile1 =
                TimeZoneFinder.createInstanceWithFallback(missingFile, validFile1);
        assertEquals("2017c", missingFileThenFile1.getIanaVersion());
        assertEquals(expectedCountryTimeZones1, missingFileThenFile1.lookupCountryTimeZones("gb"));

        TimeZoneFinder file2ThenFile1 =
                TimeZoneFinder.createInstanceWithFallback(validFile2, validFile1);
        assertEquals("2017b", file2ThenFile1.getIanaVersion());
        assertEquals(expectedCountryTimeZones2, file2ThenFile1.lookupCountryTimeZones("gb"));

        // We assume the file has been validated so an invalid file is not checked ahead of time.
        // We will find out when we look something up.
        TimeZoneFinder invalidThenValid =
                TimeZoneFinder.createInstanceWithFallback(invalidFile, validFile1);
        assertNull(invalidThenValid.getIanaVersion());
        assertNull(invalidThenValid.lookupCountryTimeZones("gb"));

        // This is not a normal case: It would imply a define shipped without a file in /system!
        TimeZoneFinder missingFiles =
                TimeZoneFinder.createInstanceWithFallback(missingFile, missingFile);
        assertNull(missingFiles.getIanaVersion());
        assertNull(missingFiles.lookupCountryTimeZones("gb"));
    }

    @Test
    public void xmlParsing_emptyFile() throws Exception {
        checkValidateThrowsParserException("");
    }

    @Test
    public void xmlParsing_unexpectedRootElement() throws Exception {
        checkValidateThrowsParserException("<foo></foo>\n");
    }

    @Test
    public void xmlParsing_missingCountryZones() throws Exception {
        checkValidateThrowsParserException("<timezones ianaversion=\"2017b\"></timezones>\n");
    }

    @Test
    public void xmlParsing_noCountriesOk() throws Exception {
        validate("<timezones ianaversion=\"2017b\">\n"
                + "  <countryzones>\n"
                + "  </countryzones>\n"
                + "</timezones>\n");
    }

    @Test
    public void xmlParsing_unexpectedComments() throws Exception {
        CountryTimeZones expectedCountryTimeZones = CountryTimeZones.createValidated(
                "gb", "Europe/London", true /* everUsesUtc */, timeZoneMappings("Europe/London"),
                "test");

        TimeZoneFinder finder = validate("<timezones ianaversion=\"2017b\">\n"
                + "  <countryzones>\n"
                + "    <country code=\"gb\" default=\"Europe/London\" everutc=\"y\">\n"
                + "      <!-- This is a comment -->"
                + "      <id>Europe/London</id>\n"
                + "    </country>\n"
                + "  </countryzones>\n"
                + "</timezones>\n");
        assertEquals(expectedCountryTimeZones, finder.lookupCountryTimeZones("gb"));

        // This is a crazy comment, but also helps prove that TEXT nodes are coalesced by the
        // parser.
        finder = validate("<timezones ianaversion=\"2017b\">\n"
                + "  <countryzones>\n"
                + "    <country code=\"gb\" default=\"Europe/London\" everutc=\"y\">\n"
                + "      <id>Europe/<!-- Don't freak out! -->London</id>\n"
                + "    </country>\n"
                + "  </countryzones>\n"
                + "</timezones>\n");
        assertEquals(expectedCountryTimeZones, finder.lookupCountryTimeZones("gb"));
    }

    @Test
    public void xmlParsing_unexpectedElementsIgnored() throws Exception {
        CountryTimeZones expectedCountryTimeZones = CountryTimeZones.createValidated(
                "gb", "Europe/London", true /* everUsesUtc */, timeZoneMappings("Europe/London"),
                "test");

        String unexpectedElement = "<unexpected-element>\n<a /></unexpected-element>\n";
        TimeZoneFinder finder = validate("<timezones ianaversion=\"2017b\">\n"
                + "  " + unexpectedElement
                + "  <countryzones>\n"
                + "    <country code=\"gb\" default=\"Europe/London\" everutc=\"y\">\n"
                + "      <id>Europe/London</id>\n"
                + "    </country>\n"
                + "  </countryzones>\n"
                + "</timezones>\n");
        assertEquals(expectedCountryTimeZones, finder.lookupCountryTimeZones("gb"));

        finder = validate("<timezones ianaversion=\"2017b\">\n"
                + "  <countryzones>\n"
                + "    " + unexpectedElement
                + "    <country code=\"gb\" default=\"Europe/London\" everutc=\"y\">\n"
                + "      <id>Europe/London</id>\n"
                + "    </country>\n"
                + "  </countryzones>\n"
                + "</timezones>\n");
        assertEquals(expectedCountryTimeZones, finder.lookupCountryTimeZones("gb"));

        finder = validate("<timezones ianaversion=\"2017b\">\n"
                + "  <countryzones>\n"
                + "    <country code=\"gb\" default=\"Europe/London\" everutc=\"y\">\n"
                + "      " + unexpectedElement
                + "      <id>Europe/London</id>\n"
                + "    </country>\n"
                + "  </countryzones>\n"
                + "</timezones>\n");
        assertEquals(expectedCountryTimeZones, finder.lookupCountryTimeZones("gb"));

        finder = validate("<timezones ianaversion=\"2017b\">\n"
                + "  <countryzones>\n"
                + "    <country code=\"gb\" default=\"Europe/London\" everutc=\"y\">\n"
                + "      <id>Europe/London</id>\n"
                + "    </country>\n"
                + "    " + unexpectedElement
                + "  </countryzones>\n"
                + "</timezones>\n");
        assertEquals(expectedCountryTimeZones, finder.lookupCountryTimeZones("gb"));

        // This test is important because it ensures we can extend the format in future with
        // more information.
        finder = validate("<timezones ianaversion=\"2017b\">\n"
                + "  <countryzones>\n"
                + "    <country code=\"gb\" default=\"Europe/London\" everutc=\"y\">\n"
                + "      <id>Europe/London</id>\n"
                + "    </country>\n"
                + "  </countryzones>\n"
                + "  " + unexpectedElement
                + "</timezones>\n");
        assertEquals(expectedCountryTimeZones, finder.lookupCountryTimeZones("gb"));

        expectedCountryTimeZones = CountryTimeZones.createValidated(
                "gb", "Europe/London", true /* everUsesUtc */,
                timeZoneMappings("Europe/London", "Europe/Paris"), "test");
        finder = validate("<timezones ianaversion=\"2017b\">\n"
                + "  <countryzones>\n"
                + "    <country code=\"gb\" default=\"Europe/London\" everutc=\"y\">\n"
                + "      <id>Europe/London</id>\n"
                + "      " + unexpectedElement
                + "      <id>Europe/Paris</id>\n"
                + "    </country>\n"
                + "  </countryzones>\n"
                + "</timezones>\n");
        assertEquals(expectedCountryTimeZones, finder.lookupCountryTimeZones("gb"));
    }

    @Test
    public void xmlParsing_unexpectedTextIgnored() throws Exception {
        CountryTimeZones expectedCountryTimeZones = CountryTimeZones.createValidated(
                "gb", "Europe/London", true /* everUsesUtc */, timeZoneMappings("Europe/London"),
                "test");

        String unexpectedText = "unexpected-text";
        TimeZoneFinder finder = validate("<timezones ianaversion=\"2017b\">\n"
                + "  " + unexpectedText
                + "  <countryzones>\n"
                + "    <country code=\"gb\" default=\"Europe/London\" everutc=\"y\">\n"
                + "      <id>Europe/London</id>\n"
                + "    </country>\n"
                + "  </countryzones>\n"
                + "</timezones>\n");
        assertEquals(expectedCountryTimeZones, finder.lookupCountryTimeZones("gb"));

        finder = validate("<timezones ianaversion=\"2017b\">\n"
                + "  <countryzones>\n"
                + "    " + unexpectedText
                + "    <country code=\"gb\" default=\"Europe/London\" everutc=\"y\">\n"
                + "      <id>Europe/London</id>\n"
                + "    </country>\n"
                + "  </countryzones>\n"
                + "</timezones>\n");
        assertEquals(expectedCountryTimeZones, finder.lookupCountryTimeZones("gb"));

        finder = validate("<timezones ianaversion=\"2017b\">\n"
                + "  <countryzones>\n"
                + "    <country code=\"gb\" default=\"Europe/London\" everutc=\"y\">\n"
                + "      " + unexpectedText
                + "      <id>Europe/London</id>\n"
                + "    </country>\n"
                + "  </countryzones>\n"
                + "</timezones>\n");
        assertEquals(expectedCountryTimeZones, finder.lookupCountryTimeZones("gb"));

        expectedCountryTimeZones = CountryTimeZones.createValidated(
                "gb", "Europe/London", true /* everUsesUtc */,
                timeZoneMappings("Europe/London", "Europe/Paris"), "test");
        finder = validate("<timezones ianaversion=\"2017b\">\n"
                + "  <countryzones>\n"
                + "    <country code=\"gb\" default=\"Europe/London\" everutc=\"y\">\n"
                + "      <id>Europe/London</id>\n"
                + "      " + unexpectedText
                + "      <id>Europe/Paris</id>\n"
                + "    </country>\n"
                + "  </countryzones>\n"
                + "</timezones>\n");
        assertEquals(expectedCountryTimeZones, finder.lookupCountryTimeZones("gb"));
    }

    @Test
    public void xmlParsing_truncatedInput() throws Exception {
        checkValidateThrowsParserException("<timezones ianaversion=\"2017b\">\n");

        checkValidateThrowsParserException("<timezones ianaversion=\"2017b\">\n"
                + "  <countryzones>\n");

        checkValidateThrowsParserException("<timezones ianaversion=\"2017b\">\n"
                + "  <countryzones>\n"
                + "    <country code=\"gb\" default=\"Europe/London\" everutc=\"y\">\n");

        checkValidateThrowsParserException("<timezones ianaversion=\"2017b\">\n"
                + "  <countryzones>\n"
                + "    <country code=\"gb\" default=\"Europe/London\" everutc=\"y\">\n"
                + "      <id>Europe/London</id>\n");

        checkValidateThrowsParserException("<timezones ianaversion=\"2017b\">\n"
                + "  <countryzones>\n"
                + "    <country code=\"gb\" default=\"Europe/London\" everutc=\"y\">\n"
                + "      <id>Europe/London</id>\n"
                + "    </country>\n");

        checkValidateThrowsParserException("<timezones ianaversion=\"2017b\">\n"
                + "  <countryzones>\n"
                + "    <country code=\"gb\" default=\"Europe/London\" everutc=\"y\">\n"
                + "      <id>Europe/London</id>\n"
                + "    </country>\n"
                + "  </countryzones>\n");
    }

    @Test
    public void xmlParsing_unexpectedChildInTimeZoneIdThrows() throws Exception {
        checkValidateThrowsParserException("<timezones ianaversion=\"2017b\">\n"
                + "  <countryzones>\n"
                + "    <country code=\"gb\" default=\"Europe/London\" everutc=\"y\">\n"
                + "      <id><unexpected-element /></id>\n"
                + "    </country>\n"
                + "  </countryzones>\n"
                + "</timezones>\n");
    }

    @Test
    public void xmlParsing_unknownTimeZoneIdIgnored() throws Exception {
        CountryTimeZones expectedCountryTimeZones = CountryTimeZones.createValidated(
                "gb", "Europe/London", true /* everUsesUtc */, timeZoneMappings("Europe/London"),
                "test");
        TimeZoneFinder finder = validate("<timezones ianaversion=\"2017b\">\n"
                + "  <countryzones>\n"
                + "    <country code=\"gb\" default=\"Europe/London\" everutc=\"y\">\n"
                + "      <id>Unknown_Id</id>\n"
                + "      <id>Europe/London</id>\n"
                + "    </country>\n"
                + "  </countryzones>\n"
                + "</timezones>\n");
        assertEquals(expectedCountryTimeZones, finder.lookupCountryTimeZones("gb"));
    }

    @Test
    public void xmlParsing_missingCountryCode() throws Exception {
        checkValidateThrowsParserException("<timezones ianaversion=\"2017b\">\n"
                + "  <countryzones>\n"
                + "    <country default=\"Europe/London\" everutc=\"y\">\n"
                + "      <id>Europe/London</id>\n"
                + "    </country>\n"
                + "  </countryzones>\n"
                + "</timezones>\n");
    }

    @Test
    public void xmlParsing_missingCountryEverUtc() throws Exception {
        checkValidateThrowsParserException("<timezones ianaversion=\"2017b\">\n"
                + "  <countryzones>\n"
                + "    <country code=\"gb\" default=\"Europe/London\">\n"
                + "      <id>Europe/London</id>\n"
                + "    </country>\n"
                + "  </countryzones>\n"
                + "</timezones>\n");
    }

    @Test
    public void xmlParsing_badCountryEverUtc() throws Exception {
        checkValidateThrowsParserException("<timezones ianaversion=\"2017b\">\n"
                + "  <countryzones>\n"
                + "    <country code=\"gb\" default=\"Europe/London\" everutc=\"occasionally\">\n"
                + "      <id>Europe/London</id>\n"
                + "    </country>\n"
                + "  </countryzones>\n"
                + "</timezones>\n");
    }

    @Test
    public void xmlParsing_missingCountryDefault() throws Exception {
        checkValidateThrowsParserException("<timezones ianaversion=\"2017b\">\n"
                + "  <countryzones>\n"
                + "    <country code=\"gb\" everutc=\"y\">\n"
                + "      <id>Europe/London</id>\n"
                + "    </country>\n"
                + "  </countryzones>\n"
                + "</timezones>\n");
    }

    @Test
    public void xmlParsing_badTimeZoneMappingPicker() throws Exception {
        checkValidateThrowsParserException("<timezones ianaversion=\"2017b\">\n"
                + "  <countryzones>\n"
                + "    <country code=\"gb\" default=\"Europe/London\" everutc=\"y\">\n"
                + "      <id picker=\"sometimes\">Europe/London</id>\n"
                + "    </country>\n"
                + "  </countryzones>\n"
                + "</timezones>\n");
    }

    @Test
    public void xmlParsing_timeZoneMappingPicker() throws Exception {
        TimeZoneFinder finder = validate("<timezones ianaversion=\"2017b\">\n"
                + "  <countryzones>\n"
                + "    <country code=\"us\" default=\"America/New_York\" everutc=\"n\">\n"
                + "      <!-- Explicit picker=\"y\" -->\n"
                + "      <id picker=\"y\">America/New_York</id>\n"
                + "      <!-- Implicit picker=\"y\" -->\n"
                + "      <id>America/Los_Angeles</id>\n"
                + "      <!-- Explicit picker=\"n\" -->\n"
                + "      <id picker=\"n\">America/Indiana/Vincennes</id>\n"
                + "    </country>\n"
                + "  </countryzones>\n"
                + "</timezones>\n");
        CountryTimeZones usTimeZones = finder.lookupCountryTimeZones("us");
        List<TimeZoneMapping> actualTimeZoneMappings = usTimeZones.getTimeZoneMappings();
        List<TimeZoneMapping> expectedTimeZoneMappings = list(
                TimeZoneMapping.createForTests(
                        "America/New_York", true /* shownInPicker */, null /* notUsedAfter */),
                TimeZoneMapping.createForTests(
                        "America/Los_Angeles", true /* shownInPicker */, null /* notUsedAfter */),
                TimeZoneMapping.createForTests(
                        "America/Indiana/Vincennes", false /* shownInPicker */,
                        null /* notUsedAfter */)
        );
        assertEquals(expectedTimeZoneMappings, actualTimeZoneMappings);
    }

    @Test
    public void xmlParsing_badTimeZoneMappingNotAfter() throws Exception {
        checkValidateThrowsParserException("<timezones ianaversion=\"2017b\">\n"
                + "  <countryzones>\n"
                + "    <country code=\"gb\" default=\"Europe/London\" everutc=\"y\">\n"
                + "      <id notafter=\"sometimes\">Europe/London</id>\n"
                + "    </country>\n"
                + "  </countryzones>\n"
                + "</timezones>\n");
    }

    @Test
    public void xmlParsing_timeZoneMappingNotAfter() throws Exception {
        TimeZoneFinder finder = validate("<timezones ianaversion=\"2017b\">\n"
                + "  <countryzones>\n"
                + "    <country code=\"us\" default=\"America/New_York\" everutc=\"n\">\n"
                + "      <!-- Explicit notafter -->\n"
                + "      <id notafter=\"1234\">America/New_York</id>\n"
                + "      <!-- Missing notafter -->\n"
                + "      <id>America/Indiana/Vincennes</id>\n"
                + "    </country>\n"
                + "  </countryzones>\n"
                + "</timezones>\n");
        CountryTimeZones usTimeZones = finder.lookupCountryTimeZones("us");
        List<TimeZoneMapping> actualTimeZoneMappings = usTimeZones.getTimeZoneMappings();
        List<TimeZoneMapping> expectedTimeZoneMappings = list(
                TimeZoneMapping.createForTests(
                        "America/New_York", true /* shownInPicker */, 1234L /* notUsedAfter */),
                TimeZoneMapping.createForTests(
                        "America/Indiana/Vincennes", true /* shownInPicker */,
                        null /* notUsedAfter */)
        );
        assertEquals(expectedTimeZoneMappings, actualTimeZoneMappings);
    }

    @Test
    public void xmlParsing_unknownCountryReturnsNull() throws Exception {
        TimeZoneFinder finder = validate("<timezones ianaversion=\"2017b\">\n"
                + "  <countryzones>\n"
                + "  </countryzones>\n"
                + "</timezones>\n");
        assertNull(finder.lookupTimeZoneIdsByCountry("gb"));
        assertNull(finder.lookupTimeZonesByCountry("gb"));
    }

    @Test
    public void getCountryZonesFinder() throws Exception {
        TimeZoneFinder timeZoneFinder = TimeZoneFinder.createInstanceForTests(
                "<timezones ianaversion=\"2017b\">\n"
                + "  <countryzones>\n"
                + "    <country code=\"gb\" default=\"Europe/London\" everutc=\"y\">\n"
                + "      <id>Europe/London</id>\n"
                + "    </country>\n"
                + "    <country code=\"fr\" default=\"Europe/Paris\" everutc=\"y\">\n"
                + "      <id>Europe/Paris</id>\n"
                + "    </country>\n"
                + "  </countryzones>\n"
                + "</timezones>\n");
        CountryTimeZones expectedGb = CountryTimeZones.createValidated("gb", "Europe/London", true,
                timeZoneMappings("Europe/London"), "test");
        CountryTimeZones expectedFr = CountryTimeZones.createValidated("fr", "Europe/Paris", true,
                timeZoneMappings("Europe/Paris"), "test");
        CountryZonesFinder countryZonesFinder = timeZoneFinder.getCountryZonesFinder();
        assertEquals(list("gb", "fr"), countryZonesFinder.lookupAllCountryIsoCodes());
        assertEquals(expectedGb, countryZonesFinder.lookupCountryTimeZones("gb"));
        assertEquals(expectedFr, countryZonesFinder.lookupCountryTimeZones("fr"));
        assertNull(countryZonesFinder.lookupCountryTimeZones("DOES_NOT_EXIST"));
    }

    @Test
    public void getCountryZonesFinder_empty() throws Exception {
        TimeZoneFinder timeZoneFinder = TimeZoneFinder.createInstanceForTests(
                "<timezones ianaversion=\"2017b\">\n"
                + "  <countryzones>\n"
                + "  </countryzones>\n"
                + "</timezones>\n");
        CountryZonesFinder countryZonesFinder = timeZoneFinder.getCountryZonesFinder();
        assertEquals(list(), countryZonesFinder.lookupAllCountryIsoCodes());
    }

    @Test
    public void getCountryZonesFinder_invalid() throws Exception {
        TimeZoneFinder timeZoneFinder = TimeZoneFinder.createInstanceForTests(
                "<timezones ianaversion=\"2017b\">\n"
                + "  <countryzones>\n"
                + "    <country code=\"gb\" default=\"Europe/London\" everutc=\"y\">\n"
                + "      <id>Europe/London</id>\n"
                + "    </country>\n"
                + "    <!-- Missing required attributes! -->\n"
                + "    <country code=\"fr\">\n"
                + "      <id>Europe/London</id>\n"
                + "    </country>\n"
                + "  </countryzones>\n"
                + "</timezones>\n");
        assertNull(timeZoneFinder.getCountryZonesFinder());
    }

    @Test
    public void lookupTimeZonesByCountry_structuresAreImmutable() throws Exception {
        TimeZoneFinder finder = validate("<timezones ianaversion=\"2017b\">\n"
                + "  <countryzones>\n"
                + "    <country code=\"gb\" default=\"Europe/London\" everutc=\"y\">\n"
                + "      <id>Europe/London</id>\n"
                + "    </country>\n"
                + "  </countryzones>\n"
                + "</timezones>\n");

        List<TimeZone> gbList = finder.lookupTimeZonesByCountry("gb");
        assertEquals(1, gbList.size());
        assertImmutableList(gbList);
        assertImmutableTimeZone(gbList.get(0));

        // Check country code normalization works too.
        assertEquals(1, finder.lookupTimeZonesByCountry("GB").size());

        assertNull(finder.lookupTimeZonesByCountry("unknown"));
    }

    @Test
    public void lookupTimeZoneIdsByCountry_structuresAreImmutable() throws Exception {
        TimeZoneFinder finder = validate("<timezones ianaversion=\"2017b\">\n"
                + "  <countryzones>\n"
                + "    <country code=\"gb\" default=\"Europe/London\" everutc=\"y\">\n"
                + "      <id>Europe/London</id>\n"
                + "    </country>\n"
                + "  </countryzones>\n"
                + "</timezones>\n");

        List<String> gbList = finder.lookupTimeZoneIdsByCountry("gb");
        assertEquals(1, gbList.size());
        assertImmutableList(gbList);

        // Check country code normalization works too.
        assertEquals(1, finder.lookupTimeZoneIdsByCountry("GB").size());

        assertNull(finder.lookupTimeZoneIdsByCountry("unknown"));
    }

    @Test
    public void lookupDefaultTimeZoneIdByCountry() throws Exception {
        TimeZoneFinder finder = validate("<timezones ianaversion=\"2017b\">\n"
                + "  <countryzones>\n"
                + "    <country code=\"gb\" default=\"Europe/London\" everutc=\"y\">\n"
                + "      <id>Europe/London</id>\n"
                + "    </country>\n"
                + "  </countryzones>\n"
                + "</timezones>\n");

        assertEquals("Europe/London", finder.lookupDefaultTimeZoneIdByCountry("gb"));

        // Check country code normalization works too.
        assertEquals("Europe/London", finder.lookupDefaultTimeZoneIdByCountry("GB"));
    }

    /**
     * At runtime we don't validate too much since there's nothing we can do if the data is
     * incorrect.
     */
    @Test
    public void lookupDefaultTimeZoneIdByCountry_notCountryTimeZoneButValid() throws Exception {
        String xml = "<timezones ianaversion=\"2017b\">\n"
                + "  <countryzones>\n"
                + "    <country code=\"gb\" default=\"America/New_York\" everutc=\"y\">\n"
                + "      <id>Europe/London</id>\n"
                + "    </country>\n"
                + "  </countryzones>\n"
                + "</timezones>\n";
        // validate() should fail because America/New_York is not one of the "gb" zones listed.
        checkValidateThrowsParserException(xml);

        // But it should still work at runtime.
        TimeZoneFinder finder = TimeZoneFinder.createInstanceForTests(xml);
        assertEquals("America/New_York", finder.lookupDefaultTimeZoneIdByCountry("gb"));
    }

    @Test
    public void lookupDefaultTimeZoneIdByCountry_invalidDefault() throws Exception {
        String xml = "<timezones ianaversion=\"2017b\">\n"
                + "  <countryzones>\n"
                + "    <country code=\"gb\" default=\"Moon/Tranquility_Base\" everutc=\"y\">\n"
                + "      <id>Europe/London</id>\n"
                + "      <id>Moon/Tranquility_Base</id>\n"
                + "    </country>\n"
                + "  </countryzones>\n"
                + "</timezones>\n";
        // validate() should pass because the IDs all match.
        TimeZoneFinder finder = validate(xml);

        // But "Moon/Tranquility_Base" is not a valid time zone ID so should not be used.
        assertNull(finder.lookupDefaultTimeZoneIdByCountry("gb"));
    }

    @Test
    public void lookupTimeZoneByCountryAndOffset_unknownCountry() throws Exception {
        TimeZoneFinder finder = validate("<timezones ianaversion=\"2017b\">\n"
                + "  <countryzones>\n"
                + "    <country code=\"xx\" default=\"Europe/London\" everutc=\"y\">\n"
                + "      <id>Europe/London</id>\n"
                + "    </country>\n"
                + "  </countryzones>\n"
                + "</timezones>\n");

        // Demonstrate the arguments work for a known country.
        assertZoneEquals(LONDON_TZ,
                finder.lookupTimeZoneByCountryAndOffset("xx", LONDON_DST_OFFSET_MILLIS,
                        true /* isDst */, WHEN_DST, null /* bias */));

        // Check country code normalization works too.
        assertZoneEquals(LONDON_TZ,
                finder.lookupTimeZoneByCountryAndOffset("XX", LONDON_DST_OFFSET_MILLIS,
                        true /* isDst */, WHEN_DST, null /* bias */));

        // Test with an unknown country.
        String unknownCountryCode = "yy";
        assertNull(finder.lookupTimeZoneByCountryAndOffset(unknownCountryCode,
                LONDON_DST_OFFSET_MILLIS, true /* isDst */, WHEN_DST, null /* bias */));

        assertNull(finder.lookupTimeZoneByCountryAndOffset(unknownCountryCode,
                LONDON_DST_OFFSET_MILLIS, true /* isDst */, WHEN_DST, LONDON_TZ /* bias */));
    }

    @Test
    public void lookupTimeZoneByCountryAndOffset_oneCandidate() throws Exception {
        TimeZoneFinder finder = validate("<timezones ianaversion=\"2017b\">\n"
                + "  <countryzones>\n"
                + "    <country code=\"xx\" default=\"Europe/London\" everutc=\"y\">\n"
                + "      <id>Europe/London</id>\n"
                + "    </country>\n"
                + "  </countryzones>\n"
                + "</timezones>\n");

        // The three parameters match the configured zone: offset, isDst and when.
        assertZoneEquals(LONDON_TZ,
                finder.lookupTimeZoneByCountryAndOffset("xx", LONDON_DST_OFFSET_MILLIS,
                        true /* isDst */, WHEN_DST, null /* bias */));
        assertZoneEquals(LONDON_TZ,
                finder.lookupTimeZoneByCountryAndOffset("xx", LONDON_NO_DST_OFFSET_MILLIS,
                        false /* isDst */, WHEN_NO_DST, null /* bias */));

        // Some lookup failure cases where the offset, isDst and when do not match the configured
        // zone.
        TimeZone noDstMatch1 = finder.lookupTimeZoneByCountryAndOffset("xx",
                LONDON_DST_OFFSET_MILLIS, true /* isDst */, WHEN_NO_DST, null /* bias */);
        assertNull(noDstMatch1);

        TimeZone noDstMatch2 = finder.lookupTimeZoneByCountryAndOffset("xx",
                LONDON_DST_OFFSET_MILLIS, false /* isDst */, WHEN_NO_DST, null /* bias */);
        assertNull(noDstMatch2);

        TimeZone noDstMatch3 = finder.lookupTimeZoneByCountryAndOffset("xx",
                LONDON_NO_DST_OFFSET_MILLIS, true /* isDst */, WHEN_DST, null /* bias */);
        assertNull(noDstMatch3);

        TimeZone noDstMatch4 = finder.lookupTimeZoneByCountryAndOffset("xx",
                LONDON_NO_DST_OFFSET_MILLIS, true /* isDst */, WHEN_NO_DST, null /* bias */);
        assertNull(noDstMatch4);

        TimeZone noDstMatch5 = finder.lookupTimeZoneByCountryAndOffset("xx",
                LONDON_DST_OFFSET_MILLIS, false /* isDst */, WHEN_DST, null /* bias */);
        assertNull(noDstMatch5);

        TimeZone noDstMatch6 = finder.lookupTimeZoneByCountryAndOffset("xx",
                LONDON_NO_DST_OFFSET_MILLIS, false /* isDst */, WHEN_DST, null /* bias */);
        assertNull(noDstMatch6);

        // Some bias cases below.

        // The bias is irrelevant here: it matches what would be returned anyway.
        assertZoneEquals(LONDON_TZ,
                finder.lookupTimeZoneByCountryAndOffset("xx", LONDON_DST_OFFSET_MILLIS,
                        true /* isDst */, WHEN_DST, LONDON_TZ /* bias */));
        assertZoneEquals(LONDON_TZ,
                finder.lookupTimeZoneByCountryAndOffset("xx", LONDON_NO_DST_OFFSET_MILLIS,
                        false /* isDst */, WHEN_NO_DST, LONDON_TZ /* bias */));
        // A sample of a non-matching case with bias.
        assertNull(finder.lookupTimeZoneByCountryAndOffset("xx", LONDON_DST_OFFSET_MILLIS,
                true /* isDst */, WHEN_NO_DST, LONDON_TZ /* bias */));

        // The bias should be ignored: it doesn't match any of the country's zones.
        assertZoneEquals(LONDON_TZ,
                finder.lookupTimeZoneByCountryAndOffset("xx", LONDON_DST_OFFSET_MILLIS,
                        true /* isDst */, WHEN_DST, NEW_YORK_TZ /* bias */));

        // The bias should still be ignored even though it matches the offset information given:
        // it doesn't match any of the country's configured zones.
        assertNull(finder.lookupTimeZoneByCountryAndOffset("xx", NEW_YORK_DST_OFFSET_MILLIS,
                true /* isDst */, WHEN_DST, NEW_YORK_TZ /* bias */));
    }

    @Test
    public void lookupTimeZoneByCountryAndOffset_multipleNonOverlappingCandidates()
            throws Exception {
        TimeZoneFinder finder = validate("<timezones ianaversion=\"2017b\">\n"
                + "  <countryzones>\n"
                + "    <country code=\"xx\" default=\"Europe/London\" everutc=\"y\">\n"
                + "      <id>America/New_York</id>\n"
                + "      <id>Europe/London</id>\n"
                + "    </country>\n"
                + "  </countryzones>\n"
                + "</timezones>\n");

        // The three parameters match the configured zone: offset, isDst and when.
        assertZoneEquals(LONDON_TZ, finder.lookupTimeZoneByCountryAndOffset("xx",
                LONDON_DST_OFFSET_MILLIS, true /* isDst */, WHEN_DST, null /* bias */));
        assertZoneEquals(LONDON_TZ, finder.lookupTimeZoneByCountryAndOffset("xx",
                LONDON_NO_DST_OFFSET_MILLIS, false /* isDst */, WHEN_NO_DST, null /* bias */));
        assertZoneEquals(NEW_YORK_TZ, finder.lookupTimeZoneByCountryAndOffset("xx",
                NEW_YORK_DST_OFFSET_MILLIS, true /* isDst */, WHEN_DST, null /* bias */));
        assertZoneEquals(NEW_YORK_TZ, finder.lookupTimeZoneByCountryAndOffset("xx",
                NEW_YORK_NO_DST_OFFSET_MILLIS, false /* isDst */, WHEN_NO_DST, null /* bias */));

        // Some lookup failure cases where the offset, isDst and when do not match the configured
        // zone. This is a sample, not complete.
        TimeZone noDstMatch1 = finder.lookupTimeZoneByCountryAndOffset("xx",
                LONDON_DST_OFFSET_MILLIS, true /* isDst */, WHEN_NO_DST, null /* bias */);
        assertNull(noDstMatch1);

        TimeZone noDstMatch2 = finder.lookupTimeZoneByCountryAndOffset("xx",
                LONDON_DST_OFFSET_MILLIS, false /* isDst */, WHEN_NO_DST, null /* bias */);
        assertNull(noDstMatch2);

        TimeZone noDstMatch3 = finder.lookupTimeZoneByCountryAndOffset("xx",
                NEW_YORK_NO_DST_OFFSET_MILLIS, true /* isDst */, WHEN_DST, null /* bias */);
        assertNull(noDstMatch3);

        TimeZone noDstMatch4 = finder.lookupTimeZoneByCountryAndOffset("xx",
                NEW_YORK_NO_DST_OFFSET_MILLIS, true /* isDst */, WHEN_NO_DST, null /* bias */);
        assertNull(noDstMatch4);

        TimeZone noDstMatch5 = finder.lookupTimeZoneByCountryAndOffset("xx",
                LONDON_DST_OFFSET_MILLIS, false /* isDst */, WHEN_DST, null /* bias */);
        assertNull(noDstMatch5);

        TimeZone noDstMatch6 = finder.lookupTimeZoneByCountryAndOffset("xx",
                LONDON_NO_DST_OFFSET_MILLIS, false /* isDst */, WHEN_DST, null /* bias */);
        assertNull(noDstMatch6);

        // Some bias cases below.

        // The bias is irrelevant here: it matches what would be returned anyway.
        assertZoneEquals(LONDON_TZ,
                finder.lookupTimeZoneByCountryAndOffset("xx", LONDON_DST_OFFSET_MILLIS,
                        true /* isDst */, WHEN_DST, LONDON_TZ /* bias */));
        assertZoneEquals(LONDON_TZ,
                finder.lookupTimeZoneByCountryAndOffset("xx", LONDON_NO_DST_OFFSET_MILLIS,
                        false /* isDst */, WHEN_NO_DST, LONDON_TZ /* bias */));
        // A sample of a non-matching case with bias.
        assertNull(finder.lookupTimeZoneByCountryAndOffset("xx", LONDON_DST_OFFSET_MILLIS,
                true /* isDst */, WHEN_NO_DST, LONDON_TZ /* bias */));

        // The bias should be ignored: it matches a configured zone, but the offset is wrong so
        // should not be considered a match.
        assertZoneEquals(LONDON_TZ,
                finder.lookupTimeZoneByCountryAndOffset("xx", LONDON_DST_OFFSET_MILLIS,
                        true /* isDst */, WHEN_DST, NEW_YORK_TZ /* bias */));
    }

    // This is an artificial case very similar to America/Denver and America/Phoenix in the US: both
    // have the same offset for 6 months of the year but diverge. Australia/Lord_Howe too.
    @Test
    public void lookupTimeZoneByCountryAndOffset_multipleOverlappingCandidates() throws Exception {
        // Three zones that have the same offset for some of the year. Europe/London changes
        // offset WHEN_DST, the others do not.
        TimeZoneFinder finder = validate("<timezones ianaversion=\"2017b\">\n"
                + "  <countryzones>\n"
                + "    <country code=\"xx\" default=\"Europe/London\" everutc=\"y\">\n"
                + "      <id>Atlantic/Reykjavik</id>\n"
                + "      <id>Europe/London</id>\n"
                + "      <id>Etc/UTC</id>\n"
                + "    </country>\n"
                + "  </countryzones>\n"
                + "</timezones>\n");

        // This is the no-DST offset for LONDON_TZ, REYKJAVIK_TZ. UTC_TZ.
        final int noDstOffset = LONDON_NO_DST_OFFSET_MILLIS;
        // This is the DST offset for LONDON_TZ.
        final int dstOffset = LONDON_DST_OFFSET_MILLIS;

        // The three parameters match the configured zone: offset, isDst and when.
        assertZoneEquals(LONDON_TZ, finder.lookupTimeZoneByCountryAndOffset("xx", dstOffset,
                true /* isDst */, WHEN_DST, null /* bias */));
        assertZoneEquals(REYKJAVIK_TZ, finder.lookupTimeZoneByCountryAndOffset("xx", noDstOffset,
                false /* isDst */, WHEN_NO_DST, null /* bias */));
        assertZoneEquals(LONDON_TZ, finder.lookupTimeZoneByCountryAndOffset("xx", dstOffset,
                true /* isDst */, WHEN_DST, null /* bias */));
        assertZoneEquals(REYKJAVIK_TZ, finder.lookupTimeZoneByCountryAndOffset("xx", noDstOffset,
                false /* isDst */, WHEN_NO_DST, null /* bias */));
        assertZoneEquals(REYKJAVIK_TZ, finder.lookupTimeZoneByCountryAndOffset("xx", noDstOffset,
                false /* isDst */, WHEN_DST, null /* bias */));

        // Some lookup failure cases where the offset, isDst and when do not match the configured
        // zones.
        TimeZone noDstMatch1 = finder.lookupTimeZoneByCountryAndOffset("xx", dstOffset,
                true /* isDst */, WHEN_NO_DST, null /* bias */);
        assertNull(noDstMatch1);

        TimeZone noDstMatch2 = finder.lookupTimeZoneByCountryAndOffset("xx", noDstOffset,
                true /* isDst */, WHEN_DST, null /* bias */);
        assertNull(noDstMatch2);

        TimeZone noDstMatch3 = finder.lookupTimeZoneByCountryAndOffset("xx", noDstOffset,
                true /* isDst */, WHEN_NO_DST, null /* bias */);
        assertNull(noDstMatch3);

        TimeZone noDstMatch4 = finder.lookupTimeZoneByCountryAndOffset("xx", dstOffset,
                false /* isDst */, WHEN_DST, null /* bias */);
        assertNull(noDstMatch4);


        // Some bias cases below.

        // The bias is relevant here: it overrides what would be returned naturally.
        assertZoneEquals(REYKJAVIK_TZ, finder.lookupTimeZoneByCountryAndOffset("xx", noDstOffset,
                false /* isDst */, WHEN_NO_DST, null /* bias */));
        assertZoneEquals(LONDON_TZ, finder.lookupTimeZoneByCountryAndOffset("xx", noDstOffset,
                false /* isDst */, WHEN_NO_DST, LONDON_TZ /* bias */));
        assertZoneEquals(UTC_TZ, finder.lookupTimeZoneByCountryAndOffset("xx", noDstOffset,
                false /* isDst */, WHEN_NO_DST, UTC_TZ /* bias */));

        // The bias should be ignored: it matches a configured zone, but the offset is wrong so
        // should not be considered a match.
        assertZoneEquals(LONDON_TZ, finder.lookupTimeZoneByCountryAndOffset("xx",
                LONDON_DST_OFFSET_MILLIS, true /* isDst */, WHEN_DST, REYKJAVIK_TZ /* bias */));
    }

    @Test
    public void xmlParsing_missingIanaVersionAttribute() throws Exception {
        // The <timezones> element will typically have an ianaversion attribute, but it's not
        // required for parsing.
        TimeZoneFinder finder = validate("<timezones>\n"
                + "  <countryzones>\n"
                + "    <country code=\"gb\" default=\"Europe/London\" everutc=\"y\">\n"
                + "      <id>Europe/London</id>\n"
                + "    </country>\n"
                + "  </countryzones>\n"
                + "</timezones>\n");
        assertEquals(list("Europe/London"), finder.lookupTimeZoneIdsByCountry("gb"));

        assertNull(finder.getIanaVersion());
    }

    @Test
    public void getIanaVersion() throws Exception {
        final String expectedIanaVersion = "2017b";

        TimeZoneFinder finder = validate("<timezones ianaversion=\"" + expectedIanaVersion + "\">\n"
                + "  <countryzones>\n"
                + "  </countryzones>\n"
                + "</timezones>\n");
        assertEquals(expectedIanaVersion, finder.getIanaVersion());
    }

    private static void assertImmutableTimeZone(TimeZone timeZone) {
        try {
            timeZone.setRawOffset(1000);
            fail();
        } catch (UnsupportedOperationException expected) {
        }
    }

    private static <X> void assertImmutableList(List<X> list) {
        try {
            list.add(null);
            fail();
        } catch (UnsupportedOperationException expected) {
        }
    }

    private static void assertZoneEquals(TimeZone expected, TimeZone actual) {
        // TimeZone.equals() only checks the ID, but that's ok for these tests.
        assertEquals(expected, actual);
    }

    private static void checkValidateThrowsParserException(String xml) {
        try {
            validate(xml);
            fail();
        } catch (IOException expected) {
        }
    }

    private static TimeZoneFinder validate(String xml) throws IOException {
        TimeZoneFinder timeZoneFinder = TimeZoneFinder.createInstanceForTests(xml);
        timeZoneFinder.validate();
        return timeZoneFinder;
    }

    /**
     * Creates a list of default {@link TimeZoneMapping} objects with the specified time zone IDs.
     */
    private static List<TimeZoneMapping> timeZoneMappings(String... timeZoneIds) {
        return Arrays.stream(timeZoneIds)
                .map(x -> TimeZoneMapping.createForTests(
                        x, true /* showInPicker */, null /* notUsedAfter */))
                .collect(Collectors.toList());
    }

    private static <X> List<X> list(X... values) {
        return Arrays.asList(values);
    }

    private static <X> List<X> sort(Collection<X> value) {
        return value.stream().sorted()
                .collect(Collectors.toList());
    }

    private String createFile(String fileContent) throws IOException {
        Path filePath = Files.createTempFile(testDir, null, null);
        Files.write(filePath, fileContent.getBytes(StandardCharsets.UTF_8));
        return filePath.toString();
    }

    private String createMissingFile() throws IOException {
        Path filePath = Files.createTempFile(testDir, null, null);
        Files.delete(filePath);
        return filePath.toString();
    }
}
