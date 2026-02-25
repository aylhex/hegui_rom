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

import android.icu.util.TimeZone;

import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;
import libcore.timezone.CountryTimeZones;
import libcore.timezone.CountryTimeZones.OffsetResult;
import libcore.timezone.CountryTimeZones.TimeZoneMapping;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertTrue;
import static org.junit.Assert.fail;

public class CountryTimeZonesTest {

    private static final int HOUR_MILLIS = 60 * 60 * 1000;

    private static final String INVALID_TZ_ID = "Moon/Tranquility_Base";

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

    // The offset applied to most zones during DST.
    private static final int NORMAL_DST_ADJUSTMENT = HOUR_MILLIS;

    private static final int LONDON_NO_DST_OFFSET_MILLIS = 0;
    private static final int LONDON_DST_OFFSET_MILLIS = LONDON_NO_DST_OFFSET_MILLIS
            + NORMAL_DST_ADJUSTMENT;

    private static final int NEW_YORK_NO_DST_OFFSET_MILLIS = -5 * HOUR_MILLIS;
    private static final int NEW_YORK_DST_OFFSET_MILLIS = NEW_YORK_NO_DST_OFFSET_MILLIS
            + NORMAL_DST_ADJUSTMENT;

    @Test
    public void createValidated() throws Exception {
        CountryTimeZones countryTimeZones = CountryTimeZones.createValidated(
                "gb", "Europe/London", true /* everUsesUtc */, timeZoneMappings("Europe/London"),
                "test");
        assertTrue(countryTimeZones.isForCountryCode("gb"));
        assertEquals("Europe/London", countryTimeZones.getDefaultTimeZoneId());
        assertZoneEquals(zone("Europe/London"), countryTimeZones.getDefaultTimeZone());
        assertEquals(timeZoneMappings("Europe/London"), countryTimeZones.getTimeZoneMappings());
        assertZonesEqual(zones("Europe/London"), countryTimeZones.getIcuTimeZones());
    }

    @Test
    public void createValidated_nullDefault() throws Exception {
        CountryTimeZones countryTimeZones = CountryTimeZones.createValidated(
                "gb", null, true /* everUsesUtc */, timeZoneMappings("Europe/London"), "test");
        assertNull(countryTimeZones.getDefaultTimeZoneId());
    }

    @Test
    public void createValidated_invalidDefault() throws Exception {
        CountryTimeZones countryTimeZones = CountryTimeZones.createValidated(
                "gb", INVALID_TZ_ID, true /* everUsesUtc */,
                timeZoneMappings("Europe/London", INVALID_TZ_ID), "test");
        assertNull(countryTimeZones.getDefaultTimeZoneId());
        assertEquals(timeZoneMappings("Europe/London"), countryTimeZones.getTimeZoneMappings());
        assertZonesEqual(zones("Europe/London"), countryTimeZones.getIcuTimeZones());
    }

    @Test
    public void createValidated_unknownTimeZoneIdIgnored() throws Exception {
        CountryTimeZones countryTimeZones = CountryTimeZones.createValidated(
                "gb", "Europe/London", true /* everUsesUtc */,
                timeZoneMappings("Unknown_Id", "Europe/London"), "test");
        assertEquals(timeZoneMappings("Europe/London"), countryTimeZones.getTimeZoneMappings());
        assertZonesEqual(zones("Europe/London"), countryTimeZones.getIcuTimeZones());
    }

    @Test
    public void isForCountryCode() throws Exception {
        CountryTimeZones countryTimeZones = CountryTimeZones.createValidated(
                "gb", "Europe/London", true /* everUsesUtc */, timeZoneMappings("Europe/London"),
                "test");
        assertTrue(countryTimeZones.isForCountryCode("GB"));
        assertTrue(countryTimeZones.isForCountryCode("Gb"));
        assertTrue(countryTimeZones.isForCountryCode("gB"));
    }

    @Test
    public void structuresAreImmutable() throws Exception {
        CountryTimeZones countryTimeZones = CountryTimeZones.createValidated(
                "gb", "Europe/London", true /* everUsesUtc */, timeZoneMappings("Europe/London"),
                "test");

        assertImmutableTimeZone(countryTimeZones.getDefaultTimeZone());

        List<TimeZone> tzList = countryTimeZones.getIcuTimeZones();
        assertEquals(1, tzList.size());
        assertImmutableList(tzList);
        assertImmutableTimeZone(tzList.get(0));

        List<TimeZoneMapping> timeZoneMappings = countryTimeZones.getTimeZoneMappings();
        assertEquals(1, timeZoneMappings.size());
        assertImmutableList(timeZoneMappings);
    }

    @Test
    public void lookupByOffsetWithBiasDeprecated_oneCandidate() throws Exception {
        CountryTimeZones countryTimeZones = CountryTimeZones.createValidated(
                "gb", "Europe/London", true /* everUsesUtc */, timeZoneMappings("Europe/London"), "test");

        OffsetResult expectedResult = new OffsetResult(LONDON_TZ, true /* oneMatch */);

        // The three parameters match the configured zone: offset, isDst and time.
        assertOffsetResultEquals(expectedResult,
                countryTimeZones.lookupByOffsetWithBias(LONDON_DST_OFFSET_MILLIS,
                        true /* isDst */, WHEN_DST, null /* bias */));
        assertOffsetResultEquals(expectedResult,
                countryTimeZones.lookupByOffsetWithBias(LONDON_NO_DST_OFFSET_MILLIS,
                        false /* isDst */, WHEN_NO_DST, null /* bias */));

        // Some lookup failure cases where the offset, isDst and time do not match the configured
        // zone.
        OffsetResult noDstMatch1 = countryTimeZones.lookupByOffsetWithBias(
                LONDON_DST_OFFSET_MILLIS, true /* isDst */, WHEN_NO_DST, null /* bias */);
        assertNull(noDstMatch1);

        OffsetResult noDstMatch2 = countryTimeZones.lookupByOffsetWithBias(
                LONDON_DST_OFFSET_MILLIS, false /* isDst */, WHEN_NO_DST, null /* bias */);
        assertNull(noDstMatch2);

        OffsetResult noDstMatch3 = countryTimeZones.lookupByOffsetWithBias(
                LONDON_NO_DST_OFFSET_MILLIS, true /* isDst */, WHEN_DST, null /* bias */);
        assertNull(noDstMatch3);

        OffsetResult noDstMatch4 = countryTimeZones.lookupByOffsetWithBias(
                LONDON_NO_DST_OFFSET_MILLIS, true /* isDst */, WHEN_NO_DST, null /* bias */);
        assertNull(noDstMatch4);

        OffsetResult noDstMatch5 = countryTimeZones.lookupByOffsetWithBias(
                LONDON_DST_OFFSET_MILLIS, false /* isDst */, WHEN_DST, null /* bias */);
        assertNull(noDstMatch5);

        OffsetResult noDstMatch6 = countryTimeZones.lookupByOffsetWithBias(
                LONDON_NO_DST_OFFSET_MILLIS, false /* isDst */, WHEN_DST, null /* bias */);
        assertNull(noDstMatch6);

        // Some bias cases below.

        // The bias is irrelevant here: it matches what would be returned anyway.
        assertOffsetResultEquals(expectedResult,
                countryTimeZones.lookupByOffsetWithBias(LONDON_DST_OFFSET_MILLIS,
                        true /* isDst */, WHEN_DST, LONDON_TZ /* bias */));
        assertOffsetResultEquals(expectedResult,
                countryTimeZones.lookupByOffsetWithBias(LONDON_NO_DST_OFFSET_MILLIS,
                        false /* isDst */, WHEN_NO_DST, LONDON_TZ /* bias */));
        // A sample of a non-matching case with bias.
        assertNull(countryTimeZones.lookupByOffsetWithBias(LONDON_DST_OFFSET_MILLIS,
                true /* isDst */, WHEN_NO_DST, LONDON_TZ /* bias */));

        // The bias should be ignored: it doesn't match any of the country's zones.
        assertOffsetResultEquals(expectedResult,
                countryTimeZones.lookupByOffsetWithBias(LONDON_DST_OFFSET_MILLIS,
                        true /* isDst */, WHEN_DST, NEW_YORK_TZ /* bias */));

        // The bias should still be ignored even though it matches the offset information given:
        // it doesn't match any of the country's configured zones.
        assertNull(countryTimeZones.lookupByOffsetWithBias(NEW_YORK_DST_OFFSET_MILLIS,
                true /* isDst */, WHEN_DST, NEW_YORK_TZ /* bias */));
    }

    @Test
    public void lookupByOffsetWithBiasDeprecated_multipleNonOverlappingCandidates()
            throws Exception {
        CountryTimeZones countryTimeZones = CountryTimeZones.createValidated(
                "xx", "Europe/London", true /* everUsesUtc */,
                timeZoneMappings("America/New_York", "Europe/London"), "test");

        OffsetResult expectedLondonResult = new OffsetResult(LONDON_TZ, true /* oneMatch */);
        OffsetResult expectedNewYorkResult = new OffsetResult(NEW_YORK_TZ, true /* oneMatch */);

        // The three parameters match the configured zone: offset, isDst and time.
        assertOffsetResultEquals(expectedLondonResult, countryTimeZones.lookupByOffsetWithBias(
                LONDON_DST_OFFSET_MILLIS, true /* isDst */, WHEN_DST, null /* bias */));
        assertOffsetResultEquals(expectedLondonResult, countryTimeZones.lookupByOffsetWithBias(
                LONDON_NO_DST_OFFSET_MILLIS, false /* isDst */, WHEN_NO_DST, null /* bias */));
        assertOffsetResultEquals(expectedNewYorkResult, countryTimeZones.lookupByOffsetWithBias(
                NEW_YORK_DST_OFFSET_MILLIS, true /* isDst */, WHEN_DST, null /* bias */));
        assertOffsetResultEquals(expectedNewYorkResult, countryTimeZones.lookupByOffsetWithBias(
                NEW_YORK_NO_DST_OFFSET_MILLIS, false /* isDst */, WHEN_NO_DST, null /* bias */));

        // Some lookup failure cases where the offset, isDst and time do not match the configured
        // zone. This is a sample, not complete.
        OffsetResult noDstMatch1 = countryTimeZones.lookupByOffsetWithBias(
                LONDON_DST_OFFSET_MILLIS, true /* isDst */, WHEN_NO_DST, null /* bias */);
        assertNull(noDstMatch1);

        OffsetResult noDstMatch2 = countryTimeZones.lookupByOffsetWithBias(
                LONDON_DST_OFFSET_MILLIS, false /* isDst */, WHEN_NO_DST, null /* bias */);
        assertNull(noDstMatch2);

        OffsetResult noDstMatch3 = countryTimeZones.lookupByOffsetWithBias(
                NEW_YORK_NO_DST_OFFSET_MILLIS, true /* isDst */, WHEN_DST, null /* bias */);
        assertNull(noDstMatch3);

        OffsetResult noDstMatch4 = countryTimeZones.lookupByOffsetWithBias(
                NEW_YORK_NO_DST_OFFSET_MILLIS, true /* isDst */, WHEN_NO_DST, null /* bias */);
        assertNull(noDstMatch4);

        OffsetResult noDstMatch5 = countryTimeZones.lookupByOffsetWithBias(
                LONDON_DST_OFFSET_MILLIS, false /* isDst */, WHEN_DST, null /* bias */);
        assertNull(noDstMatch5);

        OffsetResult noDstMatch6 = countryTimeZones.lookupByOffsetWithBias(
                LONDON_NO_DST_OFFSET_MILLIS, false /* isDst */, WHEN_DST, null /* bias */);
        assertNull(noDstMatch6);

        // Some bias cases below.

        // The bias is irrelevant here: it matches what would be returned anyway.
        assertOffsetResultEquals(expectedLondonResult, countryTimeZones.lookupByOffsetWithBias(
                LONDON_DST_OFFSET_MILLIS, true /* isDst */, WHEN_DST, LONDON_TZ /* bias */));
        assertOffsetResultEquals(expectedLondonResult, countryTimeZones.lookupByOffsetWithBias(
                LONDON_NO_DST_OFFSET_MILLIS, false /* isDst */, WHEN_NO_DST, LONDON_TZ /* bias */));
        // A sample of a non-matching case with bias.
        assertNull(countryTimeZones.lookupByOffsetWithBias(
                LONDON_DST_OFFSET_MILLIS, true /* isDst */, WHEN_NO_DST, LONDON_TZ /* bias */));

        // The bias should be ignored: it matches a configured zone, but the offset is wrong so
        // should not be considered a match.
        assertOffsetResultEquals(expectedLondonResult, countryTimeZones.lookupByOffsetWithBias(
                LONDON_DST_OFFSET_MILLIS, true /* isDst */, WHEN_DST, NEW_YORK_TZ /* bias */));
    }

    // This is an artificial case very similar to America/Denver and America/Phoenix in the US: both
    // have the same offset for 6 months of the year but diverge. Australia/Lord_Howe too.
    @Test
    public void lookupByOffsetWithBiasDeprecated_multipleOverlappingCandidates() throws Exception {
        // Three zones that have the same offset for some of the year. Europe/London changes
        // offset WHEN_DST, the others do not.
        CountryTimeZones countryTimeZones = CountryTimeZones.createValidated(
                "xx", "Europe/London", true /* everUsesUtc */,
                timeZoneMappings("Atlantic/Reykjavik", "Europe/London", "Etc/UTC"), "test");

        // This is the no-DST offset for LONDON_TZ, REYKJAVIK_TZ. UTC_TZ.
        final int noDstOffset = LONDON_NO_DST_OFFSET_MILLIS;
        // This is the DST offset for LONDON_TZ.
        final int dstOffset = LONDON_DST_OFFSET_MILLIS;

        OffsetResult expectedLondonOnlyMatch = new OffsetResult(LONDON_TZ, true /* oneMatch */);
        OffsetResult expectedReykjavikBestMatch =
                new OffsetResult(REYKJAVIK_TZ, false /* oneMatch */);

        // The three parameters match the configured zone: offset, isDst and when.
        assertOffsetResultEquals(expectedLondonOnlyMatch,
                countryTimeZones.lookupByOffsetWithBias(dstOffset, true /* isDst */, WHEN_DST,
                        null /* bias */));
        assertOffsetResultEquals(expectedReykjavikBestMatch,
                countryTimeZones.lookupByOffsetWithBias(noDstOffset, false /* isDst */, WHEN_NO_DST,
                        null /* bias */));
        assertOffsetResultEquals(expectedLondonOnlyMatch,
                countryTimeZones.lookupByOffsetWithBias(dstOffset, true /* isDst */, WHEN_DST,
                        null /* bias */));
        assertOffsetResultEquals(expectedReykjavikBestMatch,
                countryTimeZones.lookupByOffsetWithBias(noDstOffset, false /* isDst */, WHEN_NO_DST,
                        null /* bias */));
        assertOffsetResultEquals(expectedReykjavikBestMatch,
                countryTimeZones.lookupByOffsetWithBias(noDstOffset, false /* isDst */, WHEN_DST,
                        null /* bias */));

        // Some lookup failure cases where the offset, isDst and time do not match the configured
        // zones.
        OffsetResult noDstMatch1 = countryTimeZones.lookupByOffsetWithBias(dstOffset,
                true /* isDst */, WHEN_NO_DST, null /* bias */);
        assertNull(noDstMatch1);

        OffsetResult noDstMatch2 = countryTimeZones.lookupByOffsetWithBias(noDstOffset,
                true /* isDst */, WHEN_DST, null /* bias */);
        assertNull(noDstMatch2);

        OffsetResult noDstMatch3 = countryTimeZones.lookupByOffsetWithBias(noDstOffset,
                true /* isDst */, WHEN_NO_DST, null /* bias */);
        assertNull(noDstMatch3);

        OffsetResult noDstMatch4 = countryTimeZones.lookupByOffsetWithBias(dstOffset,
                false /* isDst */, WHEN_DST, null /* bias */);
        assertNull(noDstMatch4);


        // Some bias cases below.

        // Multiple zones match but Reykjavik is the bias.
        assertOffsetResultEquals(expectedReykjavikBestMatch,
                countryTimeZones.lookupByOffsetWithBias(noDstOffset, false /* isDst */, WHEN_NO_DST,
                        REYKJAVIK_TZ /* bias */));

        // Multiple zones match but London is the bias.
        OffsetResult expectedLondonBestMatch = new OffsetResult(LONDON_TZ, false /* oneMatch */);
        assertOffsetResultEquals(expectedLondonBestMatch,
                countryTimeZones.lookupByOffsetWithBias(noDstOffset, false /* isDst */, WHEN_NO_DST,
                        LONDON_TZ /* bias */));

        // Multiple zones match but UTC is the bias.
        OffsetResult expectedUtcResult = new OffsetResult(UTC_TZ, false /* oneMatch */);
        assertOffsetResultEquals(expectedUtcResult,
                countryTimeZones.lookupByOffsetWithBias(noDstOffset, false /* isDst */, WHEN_NO_DST,
                        UTC_TZ /* bias */));

        // The bias should be ignored: it matches a configured zone, but the offset is wrong so
        // should not be considered a match.
        assertOffsetResultEquals(expectedLondonOnlyMatch,
                countryTimeZones.lookupByOffsetWithBias(LONDON_DST_OFFSET_MILLIS, true /* isDst */,
                        WHEN_DST, REYKJAVIK_TZ /* bias */));
    }

    @Test
    public void lookupByOffsetWithBias_oneCandidate() throws Exception {
        CountryTimeZones countryTimeZones = CountryTimeZones.createValidated(
                "gb", "Europe/London", true /* uses UTC */, timeZoneMappings("Europe/London"),
                "test");

        OffsetResult expectedResult = new OffsetResult(LONDON_TZ, true /* oneMatch */);

        // The three parameters match the configured zone: offset, isDst and time.
        assertOffsetResultEquals(expectedResult,
                countryTimeZones.lookupByOffsetWithBias(LONDON_DST_OFFSET_MILLIS,
                        NORMAL_DST_ADJUSTMENT, WHEN_DST, null /* bias */));
        assertOffsetResultEquals(expectedResult,
                countryTimeZones.lookupByOffsetWithBias(LONDON_NO_DST_OFFSET_MILLIS,
                        0 /* no DST */, WHEN_NO_DST, null /* bias */));
        assertOffsetResultEquals(expectedResult,
                countryTimeZones.lookupByOffsetWithBias(LONDON_DST_OFFSET_MILLIS,
                        null /* unknown DST */, WHEN_DST, null /* bias */));
        assertOffsetResultEquals(expectedResult,
                countryTimeZones.lookupByOffsetWithBias(LONDON_NO_DST_OFFSET_MILLIS,
                        null /* unknown DST */, WHEN_NO_DST, null /* bias */));

        // Some lookup failure cases where the offset, DST offset and time do not match the
        // configured zone.
        OffsetResult noDstMatch1 = countryTimeZones.lookupByOffsetWithBias(
                LONDON_DST_OFFSET_MILLIS, NORMAL_DST_ADJUSTMENT, WHEN_NO_DST, null /* bias */);
        assertNull(noDstMatch1);

        OffsetResult noDstMatch2 = countryTimeZones.lookupByOffsetWithBias(
                LONDON_DST_OFFSET_MILLIS, 0 /* no DST */, WHEN_NO_DST, null /* bias */);
        assertNull(noDstMatch2);

        OffsetResult noDstMatch3 = countryTimeZones.lookupByOffsetWithBias(
                LONDON_NO_DST_OFFSET_MILLIS, NORMAL_DST_ADJUSTMENT, WHEN_DST, null /* bias */);
        assertNull(noDstMatch3);

        OffsetResult noDstMatch4 = countryTimeZones.lookupByOffsetWithBias(
                LONDON_NO_DST_OFFSET_MILLIS, NORMAL_DST_ADJUSTMENT, WHEN_NO_DST, null /* bias */);
        assertNull(noDstMatch4);

        OffsetResult noDstMatch5 = countryTimeZones.lookupByOffsetWithBias(
                LONDON_DST_OFFSET_MILLIS, 0 /* no DST */, WHEN_DST, null /* bias */);
        assertNull(noDstMatch5);

        OffsetResult noDstMatch6 = countryTimeZones.lookupByOffsetWithBias(
                LONDON_NO_DST_OFFSET_MILLIS, 0 /* no DST */, WHEN_DST, null /* bias */);
        assertNull(noDstMatch6);

        // Some bias cases below.

        // The bias is irrelevant here: it matches what would be returned anyway.
        assertOffsetResultEquals(expectedResult,
                countryTimeZones.lookupByOffsetWithBias(LONDON_DST_OFFSET_MILLIS,
                        NORMAL_DST_ADJUSTMENT, WHEN_DST, LONDON_TZ /* bias */));
        assertOffsetResultEquals(expectedResult,
                countryTimeZones.lookupByOffsetWithBias(LONDON_NO_DST_OFFSET_MILLIS,
                        0 /* no DST */, WHEN_NO_DST, LONDON_TZ /* bias */));
        assertOffsetResultEquals(expectedResult,
                countryTimeZones.lookupByOffsetWithBias(LONDON_NO_DST_OFFSET_MILLIS,
                        null /* unknown DST */, WHEN_NO_DST, LONDON_TZ /* bias */));
        // A sample of a non-matching case with bias.
        assertNull(countryTimeZones.lookupByOffsetWithBias(LONDON_DST_OFFSET_MILLIS,
                NORMAL_DST_ADJUSTMENT, WHEN_NO_DST, LONDON_TZ /* bias */));

        // The bias should be ignored: it doesn't match any of the country's zones.
        assertOffsetResultEquals(expectedResult,
                countryTimeZones.lookupByOffsetWithBias(LONDON_DST_OFFSET_MILLIS,
                        NORMAL_DST_ADJUSTMENT, WHEN_DST, NEW_YORK_TZ /* bias */));

        // The bias should still be ignored even though it matches the offset information given:
        // it doesn't match any of the country's configured zones.
        assertNull(countryTimeZones.lookupByOffsetWithBias(NEW_YORK_DST_OFFSET_MILLIS,
                NORMAL_DST_ADJUSTMENT, WHEN_DST, NEW_YORK_TZ /* bias */));
    }

    @Test
    public void lookupByOffsetWithBias_multipleNonOverlappingCandidates()
            throws Exception {
        CountryTimeZones countryTimeZones = CountryTimeZones.createValidated(
                "xx", "Europe/London", true /* uses UTC */,
                timeZoneMappings("America/New_York", "Europe/London"), "test");

        OffsetResult expectedLondonResult = new OffsetResult(LONDON_TZ, true /* oneMatch */);
        OffsetResult expectedNewYorkResult = new OffsetResult(NEW_YORK_TZ, true /* oneMatch */);

        // The three parameters match the configured zone: offset, DST offset and time.
        assertOffsetResultEquals(expectedLondonResult, countryTimeZones.lookupByOffsetWithBias(
                LONDON_DST_OFFSET_MILLIS, NORMAL_DST_ADJUSTMENT, WHEN_DST, null /* bias */));
        assertOffsetResultEquals(expectedLondonResult, countryTimeZones.lookupByOffsetWithBias(
                LONDON_NO_DST_OFFSET_MILLIS, 0 /* no DST */, WHEN_NO_DST, null /* bias */));
        assertOffsetResultEquals(expectedLondonResult, countryTimeZones.lookupByOffsetWithBias(
                LONDON_NO_DST_OFFSET_MILLIS, null /* unknown DST */, WHEN_NO_DST, null /* bias */));
        assertOffsetResultEquals(expectedNewYorkResult, countryTimeZones.lookupByOffsetWithBias(
                NEW_YORK_DST_OFFSET_MILLIS, NORMAL_DST_ADJUSTMENT, WHEN_DST, null /* bias */));
        assertOffsetResultEquals(expectedNewYorkResult, countryTimeZones.lookupByOffsetWithBias(
                NEW_YORK_NO_DST_OFFSET_MILLIS, 0 /* no DST */, WHEN_NO_DST, null /* bias */));
        assertOffsetResultEquals(expectedNewYorkResult, countryTimeZones.lookupByOffsetWithBias(
                NEW_YORK_NO_DST_OFFSET_MILLIS, null /* unknown DST */, WHEN_NO_DST,
                null /* bias */));

        // Some lookup failure cases where the offset, DST offset and time do not match the
        // configured zone. This is a sample, not complete.
        OffsetResult noDstMatch1 = countryTimeZones.lookupByOffsetWithBias(
                LONDON_DST_OFFSET_MILLIS, NORMAL_DST_ADJUSTMENT, WHEN_NO_DST, null /* bias */);
        assertNull(noDstMatch1);

        OffsetResult noDstMatch2 = countryTimeZones.lookupByOffsetWithBias(
                LONDON_DST_OFFSET_MILLIS, 0 /* no DST */, WHEN_NO_DST, null /* bias */);
        assertNull(noDstMatch2);

        OffsetResult noDstMatch3 = countryTimeZones.lookupByOffsetWithBias(
                NEW_YORK_NO_DST_OFFSET_MILLIS, NORMAL_DST_ADJUSTMENT, WHEN_DST, null /* bias */);
        assertNull(noDstMatch3);

        OffsetResult noDstMatch4 = countryTimeZones.lookupByOffsetWithBias(
                NEW_YORK_NO_DST_OFFSET_MILLIS, NORMAL_DST_ADJUSTMENT, WHEN_NO_DST, null /* bias */);
        assertNull(noDstMatch4);

        OffsetResult noDstMatch5 = countryTimeZones.lookupByOffsetWithBias(
                LONDON_DST_OFFSET_MILLIS, 0 /* no DST */, WHEN_DST, null /* bias */);
        assertNull(noDstMatch5);

        OffsetResult noDstMatch6 = countryTimeZones.lookupByOffsetWithBias(
                LONDON_NO_DST_OFFSET_MILLIS, 0 /* no DST */, WHEN_DST, null /* bias */);
        assertNull(noDstMatch6);

        // Some bias cases below.

        // The bias is irrelevant here: it matches what would be returned anyway.
        assertOffsetResultEquals(expectedLondonResult, countryTimeZones.lookupByOffsetWithBias(
                LONDON_DST_OFFSET_MILLIS, NORMAL_DST_ADJUSTMENT, WHEN_DST, LONDON_TZ /* bias */));
        assertOffsetResultEquals(expectedLondonResult, countryTimeZones.lookupByOffsetWithBias(
                LONDON_NO_DST_OFFSET_MILLIS, 0 /* no DST */, WHEN_NO_DST, LONDON_TZ /* bias */));
        assertOffsetResultEquals(expectedLondonResult, countryTimeZones.lookupByOffsetWithBias(
                LONDON_NO_DST_OFFSET_MILLIS, null /* unknown DST */, WHEN_NO_DST,
                LONDON_TZ /* bias */));

        // A sample of a non-matching case with bias.
        assertNull(countryTimeZones.lookupByOffsetWithBias(
                LONDON_DST_OFFSET_MILLIS, NORMAL_DST_ADJUSTMENT, WHEN_NO_DST, LONDON_TZ /* bias */));

        // The bias should be ignored: it matches a configured zone, but the offset is wrong so
        // should not be considered a match.
        assertOffsetResultEquals(expectedLondonResult, countryTimeZones.lookupByOffsetWithBias(
                LONDON_DST_OFFSET_MILLIS, NORMAL_DST_ADJUSTMENT, WHEN_DST, NEW_YORK_TZ /* bias */));
    }

    // This is an artificial case very similar to America/Denver and America/Phoenix in the US: both
    // have the same offset for 6 months of the year but diverge. Australia/Lord_Howe too.
    @Test
    public void lookupByOffsetWithBias_multipleOverlappingCandidates() throws Exception {
        // Three zones that have the same offset for some of the year. Europe/London changes
        // offset WHEN_DST, the others do not.
        CountryTimeZones countryTimeZones = CountryTimeZones.createValidated(
                "xx", "Europe/London", true /* uses UTC */,
                timeZoneMappings("Atlantic/Reykjavik", "Europe/London", "Etc/UTC"), "test");

        // This is the no-DST offset for LONDON_TZ, REYKJAVIK_TZ. UTC_TZ.
        final int noDstOffset = LONDON_NO_DST_OFFSET_MILLIS;
        // This is the DST offset for LONDON_TZ.
        final int dstOffset = LONDON_DST_OFFSET_MILLIS;

        OffsetResult expectedLondonOnlyMatch = new OffsetResult(LONDON_TZ, true /* oneMatch */);
        OffsetResult expectedReykjavikBestMatch =
                new OffsetResult(REYKJAVIK_TZ, false /* oneMatch */);

        // The three parameters match the configured zone: offset, DST offset and time.
        assertOffsetResultEquals(expectedLondonOnlyMatch,
                countryTimeZones.lookupByOffsetWithBias(dstOffset, NORMAL_DST_ADJUSTMENT, WHEN_DST,
                        null /* bias */));
        assertOffsetResultEquals(expectedReykjavikBestMatch,
                countryTimeZones.lookupByOffsetWithBias(noDstOffset, 0 /* no DST */, WHEN_NO_DST,
                        null /* bias */));
        assertOffsetResultEquals(expectedLondonOnlyMatch,
                countryTimeZones.lookupByOffsetWithBias(dstOffset, NORMAL_DST_ADJUSTMENT, WHEN_DST,
                        null /* bias */));
        assertOffsetResultEquals(expectedReykjavikBestMatch,
                countryTimeZones.lookupByOffsetWithBias(noDstOffset, 0 /* no DST */, WHEN_NO_DST,
                        null /* bias */));
        assertOffsetResultEquals(expectedReykjavikBestMatch,
                countryTimeZones.lookupByOffsetWithBias(noDstOffset, 0 /* no DST */, WHEN_DST,
                        null /* bias */));

        // Unknown DST cases
        assertOffsetResultEquals(expectedReykjavikBestMatch,
                countryTimeZones.lookupByOffsetWithBias(noDstOffset, null, WHEN_NO_DST,
                        null /* bias */));
        assertOffsetResultEquals(expectedReykjavikBestMatch,
                countryTimeZones.lookupByOffsetWithBias(noDstOffset, null, WHEN_DST,
                        null /* bias */));
        assertNull(countryTimeZones.lookupByOffsetWithBias(dstOffset, null, WHEN_NO_DST,
                        null /* bias */));
        assertOffsetResultEquals(expectedLondonOnlyMatch,
                countryTimeZones.lookupByOffsetWithBias(dstOffset, null, WHEN_DST,
                        null /* bias */));

        // Some lookup failure cases where the offset, DST offset and time do not match the
        // configured zones.
        OffsetResult noDstMatch1 = countryTimeZones.lookupByOffsetWithBias(dstOffset,
                NORMAL_DST_ADJUSTMENT, WHEN_NO_DST, null /* bias */);
        assertNull(noDstMatch1);

        OffsetResult noDstMatch2 = countryTimeZones.lookupByOffsetWithBias(noDstOffset,
                NORMAL_DST_ADJUSTMENT, WHEN_DST, null /* bias */);
        assertNull(noDstMatch2);

        OffsetResult noDstMatch3 = countryTimeZones.lookupByOffsetWithBias(noDstOffset,
                NORMAL_DST_ADJUSTMENT, WHEN_NO_DST, null /* bias */);
        assertNull(noDstMatch3);

        OffsetResult noDstMatch4 = countryTimeZones.lookupByOffsetWithBias(dstOffset,
                0 /* no DST */, WHEN_DST, null /* bias */);
        assertNull(noDstMatch4);


        // Some bias cases below.

        // Multiple zones match but Reykjavik is the bias.
        assertOffsetResultEquals(expectedReykjavikBestMatch,
                countryTimeZones.lookupByOffsetWithBias(noDstOffset, 0 /* no DST */, WHEN_NO_DST,
                        REYKJAVIK_TZ /* bias */));
        assertOffsetResultEquals(expectedReykjavikBestMatch,
                countryTimeZones.lookupByOffsetWithBias(noDstOffset, null /* unknown DST */,
                        WHEN_NO_DST, REYKJAVIK_TZ /* bias */));

        // Multiple zones match but London is the bias.
        OffsetResult expectedLondonBestMatch = new OffsetResult(LONDON_TZ, false /* oneMatch */);
        assertOffsetResultEquals(expectedLondonBestMatch,
                countryTimeZones.lookupByOffsetWithBias(noDstOffset, 0 /* no DST */, WHEN_NO_DST,
                        LONDON_TZ /* bias */));
        assertOffsetResultEquals(expectedLondonBestMatch,
                countryTimeZones.lookupByOffsetWithBias(noDstOffset, null /* unknown DST */,
                        WHEN_NO_DST, LONDON_TZ /* bias */));

        // Multiple zones match but UTC is the bias.
        OffsetResult expectedUtcResult = new OffsetResult(UTC_TZ, false /* oneMatch */);
        assertOffsetResultEquals(expectedUtcResult,
                countryTimeZones.lookupByOffsetWithBias(noDstOffset, 0 /* no DST */, WHEN_NO_DST,
                        UTC_TZ /* bias */));
        assertOffsetResultEquals(expectedUtcResult,
                countryTimeZones.lookupByOffsetWithBias(noDstOffset, null /* unknown DST */,
                        WHEN_NO_DST, UTC_TZ /* bias */));

        // The bias should be ignored: it matches a configured zone, but the offset is wrong so
        // should not be considered a match.
        assertOffsetResultEquals(expectedLondonOnlyMatch,
                countryTimeZones.lookupByOffsetWithBias(LONDON_DST_OFFSET_MILLIS,
                        NORMAL_DST_ADJUSTMENT, WHEN_DST, REYKJAVIK_TZ /* bias */));
    }

    @Test
    public void isDefaultOkForCountryTimeZoneDetection_noZones() {
        CountryTimeZones countryTimeZones = CountryTimeZones.createValidated(
                "xx", "Europe/London", true /* everUsesUtc */, timeZoneMappings(), "test");
        assertFalse(countryTimeZones.isDefaultOkForCountryTimeZoneDetection(WHEN_DST));
        assertFalse(countryTimeZones.isDefaultOkForCountryTimeZoneDetection(WHEN_NO_DST));
    }

    @Test
    public void isDefaultOkForCountryTimeZoneDetection_oneZone() {
        CountryTimeZones countryTimeZones = CountryTimeZones.createValidated(
                "xx", "Europe/London", true /* everUsesUtc */, timeZoneMappings("Europe/London"),
                "test");
        assertTrue(countryTimeZones.isDefaultOkForCountryTimeZoneDetection(WHEN_DST));
        assertTrue(countryTimeZones.isDefaultOkForCountryTimeZoneDetection(WHEN_NO_DST));
    }

    @Test
    public void isDefaultOkForCountryTimeZoneDetection_twoZones_overlap() {
        CountryTimeZones countryTimeZones = CountryTimeZones.createValidated(
                "xx", "Europe/London", true /* everUsesUtc */,
                timeZoneMappings("Europe/London", "Etc/UTC"), "test");
        // Europe/London is the same as UTC in the Winter, so all the zones have the same offset
        // in Winter, but not in Summer.
        assertFalse(countryTimeZones.isDefaultOkForCountryTimeZoneDetection(WHEN_DST));
        assertTrue(countryTimeZones.isDefaultOkForCountryTimeZoneDetection(WHEN_NO_DST));
    }

    @Test
    public void isDefaultOkForCountryTimeZoneDetection_twoZones_noOverlap() {
        CountryTimeZones countryTimeZones = CountryTimeZones.createValidated(
                "xx", "Europe/London", true /* everUsesUtc */,
                timeZoneMappings("Europe/London", "America/New_York"), "test");
        // The zones have different offsets all year, so it would never be ok to use the default
        // zone for the country of "xx".
        assertFalse(countryTimeZones.isDefaultOkForCountryTimeZoneDetection(WHEN_DST));
        assertFalse(countryTimeZones.isDefaultOkForCountryTimeZoneDetection(WHEN_NO_DST));
    }

    @Test
    public void hasUtcZone_everUseUtcHintOverridesZoneInformation() {
        // The country has a single zone. Europe/London uses UTC in Winter.
        CountryTimeZones countryTimeZones = CountryTimeZones.createValidated(
                "xx", "Etc/UTC", false /* everUsesUtc */, timeZoneMappings("Etc/UTC"), "test");
        assertFalse(countryTimeZones.hasUtcZone(WHEN_DST));
        assertFalse(countryTimeZones.hasUtcZone(WHEN_NO_DST));
    }

    @Test
    public void hasUtcZone_singleZone() {
        // The country has a single zone. Europe/London uses UTC in Winter.
        CountryTimeZones countryTimeZones = CountryTimeZones.createValidated(
                "xx", "Europe/London", true /* everUsesUtc */, timeZoneMappings("Europe/London"),
                "test");
        assertFalse(countryTimeZones.hasUtcZone(WHEN_DST));
        assertTrue(countryTimeZones.hasUtcZone(WHEN_NO_DST));
    }

    @Test
    public void hasUtcZone_multipleZonesWithUtc() {
        // The country has multiple zones. Europe/London uses UTC in Winter.
        CountryTimeZones countryTimeZones = CountryTimeZones.createValidated(
                "xx", "America/Los_Angeles", true /* everUsesUtc */,
                timeZoneMappings("America/Los_Angeles", "America/New_York", "Europe/London"),
                "test");
        assertFalse(countryTimeZones.hasUtcZone(WHEN_DST));
        assertTrue(countryTimeZones.hasUtcZone(WHEN_NO_DST));
    }

    @Test
    public void hasUtcZone_multipleZonesWithoutUtc() {
        // The country has multiple zones, none of which use UTC.
        CountryTimeZones countryTimeZones = CountryTimeZones.createValidated(
                "xx", "Europe/Paris", false /* everUsesUtc */,
                timeZoneMappings("America/Los_Angeles", "America/New_York", "Europe/Paris"),
                "test");
        assertFalse(countryTimeZones.hasUtcZone(WHEN_DST));
        assertFalse(countryTimeZones.hasUtcZone(WHEN_NO_DST));
    }

    @Test
    public void hasUtcZone_emptyZones() {
        // The country has no valid zones.
        CountryTimeZones countryTimeZones = CountryTimeZones.createValidated(
                "xx", INVALID_TZ_ID, false /* everUsesUtc */, timeZoneMappings(INVALID_TZ_ID),
                "test");
        assertTrue(countryTimeZones.getTimeZoneMappings().isEmpty());
        assertFalse(countryTimeZones.hasUtcZone(WHEN_DST));
        assertFalse(countryTimeZones.hasUtcZone(WHEN_NO_DST));
    }

    private void assertImmutableTimeZone(TimeZone timeZone) {
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

    private static void assertOffsetResultEquals(OffsetResult expected, OffsetResult actual) {
        assertEquals(expected.mTimeZone.getID(), actual.mTimeZone.getID());
        assertEquals(expected.mOneMatch, actual.mOneMatch);
    }

    private static void assertZonesEqual(List<TimeZone> expected, List<TimeZone> actual) {
        // TimeZone.equals() only checks the ID, but that's ok for these tests.
        assertEquals(expected, actual);
    }

    private static TimeZone zone(String id) {
        return TimeZone.getTimeZone(id);
    }

    /**
     * Creates a list of default {@link TimeZoneMapping} objects with the specified time zone IDs.
     */
    private static List<TimeZoneMapping> timeZoneMappings(String... timeZoneIds) {
        return Arrays.stream(timeZoneIds)
                .map(x -> TimeZoneMapping.createForTests(
                        x, true /* picker */, null /* notUsedAfter */))
                .collect(Collectors.toList());
    }

    private static List<TimeZone> zones(String... ids) {
        return Arrays.stream(ids).map(TimeZone::getTimeZone).collect(Collectors.toList());
    }
}
