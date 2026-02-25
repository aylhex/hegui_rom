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
package libcore.java.time.chrono;

import org.junit.Test;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.time.chrono.ChronoZonedDateTime;
import java.time.chrono.JapaneseChronology;
import java.time.chrono.JapaneseDate;
import java.time.chrono.JapaneseEra;
import java.time.temporal.ChronoField;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertSame;

/**
 * Additional tests for {@link JapaneseChronology} and {@link JapaneseDate}.
 *
 * @see tck.java.time.chrono.TCKJapaneseChronology
 */
public class JapaneseChronologyTest {

    @Test
    public void test_zonedDateTime() {
        ZonedDateTime zonedDateTime = ZonedDateTime
                .of(2017, 4, 1, 15, 14, 13, 12, ZoneId.of("Europe/London"));

        ChronoZonedDateTime<JapaneseDate> result = JapaneseChronology.INSTANCE
                .zonedDateTime(zonedDateTime.toInstant(), zonedDateTime.getZone());
        assertEquals(JapaneseDate.of(JapaneseEra.HEISEI, 29, 4, 1), result.toLocalDate());
        assertEquals(LocalTime.of(15, 14, 13, 12), result.toLocalTime());
        assertEquals(ZoneOffset.ofHours(1), result.getOffset());
    }

    @Test(expected = NullPointerException.class)
    public void test_zonedDateTime_nullInstant() {
        JapaneseChronology.INSTANCE.zonedDateTime(null, ZoneOffset.UTC);
    }

    @Test(expected = NullPointerException.class)
    public void test_zonedDateTime_nullZone() {
        JapaneseChronology.INSTANCE.zonedDateTime(Instant.EPOCH, null);
    }

    @Test
    public void test_JapaneseDate_getChronology() {
        assertSame(JapaneseChronology.INSTANCE, JapaneseDate.now().getChronology());
    }

    @Test
    public void test_JapaneseDate_getEra() {
        // pick the first january of the second year of each era, except for Meiji, because the
        // first supported year in JapaneseChronology is Meiji 6.
        assertEquals(JapaneseEra.MEIJI, JapaneseDate.from(LocalDate.of(1873, 1, 1)).getEra());
        assertEquals(JapaneseEra.TAISHO, JapaneseDate.from(LocalDate.of(1913, 1, 1)).getEra());
        assertEquals(JapaneseEra.SHOWA, JapaneseDate.from(LocalDate.of(1927, 1, 1)).getEra());
        assertEquals(JapaneseEra.HEISEI, JapaneseDate.from(LocalDate.of(1990, 1, 1)).getEra());
    }

    @Test
    public void test_JapaneseDate_isSupported_TemporalField() {
        JapaneseDate date = JapaneseDate.now();
        // all date based fields, except for the aligned week ones are supported.
        assertEquals(false, date.isSupported(ChronoField.ALIGNED_DAY_OF_WEEK_IN_MONTH));
        assertEquals(false, date.isSupported(ChronoField.ALIGNED_DAY_OF_WEEK_IN_YEAR));
        assertEquals(false, date.isSupported(ChronoField.ALIGNED_WEEK_OF_MONTH));
        assertEquals(false, date.isSupported(ChronoField.ALIGNED_WEEK_OF_YEAR));
        assertEquals(false, date.isSupported(ChronoField.AMPM_OF_DAY));
        assertEquals(false, date.isSupported(ChronoField.CLOCK_HOUR_OF_AMPM));
        assertEquals(false, date.isSupported(ChronoField.CLOCK_HOUR_OF_DAY));
        assertEquals(true, date.isSupported(ChronoField.DAY_OF_MONTH));
        assertEquals(true, date.isSupported(ChronoField.DAY_OF_WEEK));
        assertEquals(true, date.isSupported(ChronoField.DAY_OF_YEAR));
        assertEquals(true, date.isSupported(ChronoField.EPOCH_DAY));
        assertEquals(true, date.isSupported(ChronoField.ERA));
        assertEquals(false, date.isSupported(ChronoField.HOUR_OF_AMPM));
        assertEquals(false, date.isSupported(ChronoField.HOUR_OF_DAY));
        assertEquals(false, date.isSupported(ChronoField.INSTANT_SECONDS));
        assertEquals(false, date.isSupported(ChronoField.MICRO_OF_DAY));
        assertEquals(false, date.isSupported(ChronoField.MICRO_OF_SECOND));
        assertEquals(false, date.isSupported(ChronoField.MILLI_OF_DAY));
        assertEquals(false, date.isSupported(ChronoField.MILLI_OF_SECOND));
        assertEquals(false, date.isSupported(ChronoField.MINUTE_OF_DAY));
        assertEquals(false, date.isSupported(ChronoField.MINUTE_OF_HOUR));
        assertEquals(true, date.isSupported(ChronoField.MONTH_OF_YEAR));
        assertEquals(false, date.isSupported(ChronoField.NANO_OF_DAY));
        assertEquals(false, date.isSupported(ChronoField.NANO_OF_SECOND));
        assertEquals(false, date.isSupported(ChronoField.OFFSET_SECONDS));
        assertEquals(true, date.isSupported(ChronoField.PROLEPTIC_MONTH));
        assertEquals(false, date.isSupported(ChronoField.SECOND_OF_DAY));
        assertEquals(false, date.isSupported(ChronoField.SECOND_OF_MINUTE));
        assertEquals(true, date.isSupported(ChronoField.YEAR));
        assertEquals(true, date.isSupported(ChronoField.YEAR_OF_ERA));
    }
}
