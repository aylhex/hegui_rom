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

import org.junit.Test;
import android.icu.text.AlphabeticIndex;
import android.icu.text.UnicodeSet;
import android.icu.util.LocaleData;
import android.icu.util.ULocale;
import java.util.Locale;

import static org.junit.Assert.assertTrue;
import static org.junit.Assert.assertNotNull;

/**
 * Test for {@link android.icu.text.AlphabeticIndex}
 */
public class AlphabeticIndexTest {

    @Test
    public void test_english() {
        verifyIndex(Locale.ENGLISH);
    }

    // http://b/64953401
    @Test
    public void testBucketCount_withNoIndexCharacters() {
        Locale localeWithNoIndexCharacters = null;
        // Search in the available languages only instead of all possible locales
        // in order to speed-up the test.
        for (String language : Locale.getISOLanguages()) {
            Locale locale = Locale.forLanguageTag(language);
            UnicodeSet exemplarSet = LocaleData.getExemplarSet(
                ULocale.forLocale(locale), 0, LocaleData.ES_INDEX);
            if (exemplarSet == null || exemplarSet.isEmpty()) {
                localeWithNoIndexCharacters = locale;
                break;
            }
        }

        assertNotNull("Can't find any language with no index characters",
            localeWithNoIndexCharacters);

        // If this assert fails it means that it can't find any language with no index character.
        // If that's the case, please find expand the search space to find a locale that's missing
        // that key where the logic in AlphabeticIndex.addIndexExemplars will generate buckets from
        // alternate data.
        verifyIndex(localeWithNoIndexCharacters);
    }

    private void verifyIndex(Locale locale) {
        ULocale uLocale = ULocale.forLocale(locale);
        AlphabeticIndex index = new AlphabeticIndex(uLocale);
        LocaleData localeData = LocaleData.getInstance(uLocale);

        // 0 = "default options", there is no constant for this.
        UnicodeSet exemplarSet = localeData.getExemplarSet(0, LocaleData.ES_STANDARD);
        for (String s : exemplarSet) {
            index.addRecord(s, s);
        }
        assertTrue("Locale(" + locale + ") does not have enough buckets: " + index.getBucketLabels(),
            index.getBucketCount() > 1);
    }
}
