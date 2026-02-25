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
package libcore.libcore.icu;

import android.icu.util.LocaleData;
import android.icu.util.ULocale;

import org.junit.Test;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNotNull;

/**
 * Test for {@link android.icu.util.LocaleData}. Don't confuse with {@link libcore.icu.LocaleData}.
 */
public class ICULocaleDataTest {

    @Test
    public void testGetDelimiter() {
        LocaleData usLocaleData = LocaleData.getInstance(ULocale.US);
        assertEquals("“", usLocaleData.getDelimiter(LocaleData.QUOTATION_START));
        assertEquals("”", usLocaleData.getDelimiter(LocaleData.QUOTATION_END));
        assertEquals("‘", usLocaleData.getDelimiter(LocaleData.ALT_QUOTATION_START));
        assertEquals("’", usLocaleData.getDelimiter(LocaleData.ALT_QUOTATION_END));
        LocaleData italianLocaleData = LocaleData.getInstance(ULocale.ITALIAN);
        assertEquals("«", italianLocaleData.getDelimiter(LocaleData.QUOTATION_START));
        assertEquals("»", italianLocaleData.getDelimiter(LocaleData.QUOTATION_END));
        assertEquals("“", italianLocaleData.getDelimiter(LocaleData.ALT_QUOTATION_START));
        assertEquals("”", italianLocaleData.getDelimiter(LocaleData.ALT_QUOTATION_END));

        for (ULocale locale : ULocale.getAvailableLocales()) {
            LocaleData localeData = LocaleData.getInstance(locale);
            for (int type = LocaleData.QUOTATION_START; type <= LocaleData.ALT_QUOTATION_END;
                    type++) {
                String delimiter = localeData.getDelimiter(type);
                assertNotNull("Delimiter is null in this locale " + locale, delimiter);
                assertFalse("Delimiter is empty in this locale " + locale, delimiter.isEmpty());
            }
        }
    }
}