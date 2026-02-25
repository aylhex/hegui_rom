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

package libcore.heapdumper;

import java.text.Collator;
import java.util.Arrays;
import java.util.Locale;

/**
 * An enumeration of actions for which we'd like to measure the effect on the post-GC heap.
 */
enum Actions implements Runnable {

    /**
     * Does nothing. Exists to measure the overhead inherent in the measurement system.
     */
    NOOP {
        @Override
        public void run() {
            // noop!
        }
    },

    /**
     * Uses a collator for the root locale to trivially sort some strings.
     */
    COLLATOR_ROOT_LOCALE {
        @Override
        public void run() {
            useCollatorForLocale(Locale.ROOT);
        }
    },

    /**
     * Uses a collator for the US English locale to trivially sort some strings.
     */
    COLLATOR_EN_US_LOCALE {
        @Override
        public void run() {
            useCollatorForLocale(Locale.US);
        }
    },

    /**
     * Uses a collator for the Korean locale to trivially sort some strings.
     */
    COLLATOR_KOREAN_LOCALE {
        @Override
        public void run() {
            useCollatorForLocale(Locale.KOREAN);
        }
    },

    ;

    private static void useCollatorForLocale(Locale locale) {
        String[] strings = { "caff", "café", "cafe", "안녕", "잘 가" };
        Collator collator = Collator.getInstance(locale);
        Arrays.sort(strings, collator);
    }
}
