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

package libcore.libcore.timezone;

import org.junit.Test;

import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;
import libcore.timezone.CountryTimeZones;
import libcore.timezone.CountryTimeZones.TimeZoneMapping;
import libcore.timezone.CountryZonesFinder;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertSame;
import static org.junit.Assert.fail;

public class CountryZonesFinderTest {

    private static final CountryTimeZones GB_ZONES = CountryTimeZones.createValidated(
            "gb", "Europe/London", true, timeZoneMappings("Europe/London"), "test");

    private static final CountryTimeZones IM_ZONES = CountryTimeZones.createValidated(
            "im", "Europe/London", true, timeZoneMappings("Europe/London"), "test");

    private static final CountryTimeZones FR_ZONES = CountryTimeZones.createValidated(
            "fr", "Europe/Paris", true, timeZoneMappings("Europe/Paris"), "test");

    private static final CountryTimeZones US_ZONES = CountryTimeZones.createValidated(
            "us", "America/New_York", true,
            timeZoneMappings("America/New_York", "America/Los_Angeles"), "test");

    @Test
    public void lookupAllCountryIsoCodes() throws Exception {
        CountryZonesFinder countryZonesFinder =
                CountryZonesFinder.createForTests(list(GB_ZONES, FR_ZONES));

        List<String> isoList = countryZonesFinder.lookupAllCountryIsoCodes();
        assertEqualsAndImmutable(list(GB_ZONES.getCountryIso(), FR_ZONES.getCountryIso()), isoList);
    }

    @Test
    public void lookupAllCountryIsoCodes_empty() throws Exception {
        CountryZonesFinder countryZonesFinder = CountryZonesFinder.createForTests(list());
        List<String> isoList = countryZonesFinder.lookupAllCountryIsoCodes();
        assertEqualsAndImmutable(list(), isoList);
    }

    @Test
    public void lookupCountryCodesForZoneId() throws Exception {
        CountryZonesFinder countryZonesFinder =
                CountryZonesFinder.createForTests(list(GB_ZONES, IM_ZONES, FR_ZONES, US_ZONES));

        assertEqualsAndImmutable(list(GB_ZONES, IM_ZONES),
                countryZonesFinder.lookupCountryTimeZonesForZoneId("Europe/London"));
        assertEqualsAndImmutable(list(US_ZONES),
                countryZonesFinder.lookupCountryTimeZonesForZoneId("America/New_York"));
        assertEqualsAndImmutable(list(US_ZONES),
                countryZonesFinder.lookupCountryTimeZonesForZoneId("America/Los_Angeles"));
        assertEqualsAndImmutable(list(),
                countryZonesFinder.lookupCountryTimeZonesForZoneId("DOES_NOT_EXIST"));
    }

    @Test
    public void lookupCountryTimeZones() throws Exception {
        CountryZonesFinder countryZonesFinder =
                CountryZonesFinder.createForTests(list(GB_ZONES, IM_ZONES, FR_ZONES, US_ZONES));
        assertSame(GB_ZONES, countryZonesFinder.lookupCountryTimeZones(GB_ZONES.getCountryIso()));
        assertSame(IM_ZONES, countryZonesFinder.lookupCountryTimeZones(IM_ZONES.getCountryIso()));
        assertNull(countryZonesFinder.lookupCountryTimeZones("DOES_NOT_EXIST"));
    }

    private static <X> void assertEqualsAndImmutable(List<X> expected, List<X> actual) {
        assertEquals(expected, actual);
        assertImmutableList(actual);
    }

    private static <X> void assertImmutableList(List<X> list) {
        try {
            list.add(null);
            fail();
        } catch (UnsupportedOperationException expected) {
        }
    }

    private static <X> List<X> list(X... values) {
        return Arrays.asList(values);
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
}
