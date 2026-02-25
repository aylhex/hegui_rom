/*
 * Copyright (C) 2014 The Android Open Source Project
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

package libcore.libcore.net;

import libcore.net.MimeUtils;

import junit.framework.TestCase;

import java.util.Locale;
import java.util.Objects;

public class MimeUtilsTest extends TestCase {
    public void test_15715370() {
        assertEquals("audio/flac", MimeUtils.guessMimeTypeFromExtension("flac"));
        assertEquals("flac", MimeUtils.guessExtensionFromMimeType("audio/flac"));
        assertEquals("flac", MimeUtils.guessExtensionFromMimeType("application/x-flac"));
    }

    // https://code.google.com/p/android/issues/detail?id=78909
    public void test_78909() {
        assertEquals("mka", MimeUtils.guessExtensionFromMimeType("audio/x-matroska"));
        assertEquals("mkv", MimeUtils.guessExtensionFromMimeType("video/x-matroska"));
    }

    public void test_16978217() {
        assertEquals("image/x-ms-bmp", MimeUtils.guessMimeTypeFromExtension("bmp"));
        assertEquals("image/x-icon", MimeUtils.guessMimeTypeFromExtension("ico"));
        assertEquals("video/mp2ts", MimeUtils.guessMimeTypeFromExtension("ts"));
    }

    public void testCommon() {
        assertEquals("audio/mpeg", MimeUtils.guessMimeTypeFromExtension("mp3"));
        assertEquals("image/png", MimeUtils.guessMimeTypeFromExtension("png"));
        assertEquals("application/zip", MimeUtils.guessMimeTypeFromExtension("zip"));

        assertEquals("mp3", MimeUtils.guessExtensionFromMimeType("audio/mpeg"));
        assertEquals("png", MimeUtils.guessExtensionFromMimeType("image/png"));
        assertEquals("zip", MimeUtils.guessExtensionFromMimeType("application/zip"));
    }

    public void test_18390752() {
        assertEquals("jpg", MimeUtils.guessExtensionFromMimeType("image/jpeg"));
    }

    public void test_30207891() {
        assertTrue(MimeUtils.hasMimeType("IMAGE/PNG"));
        assertTrue(MimeUtils.hasMimeType("IMAGE/png"));
        assertFalse(MimeUtils.hasMimeType(""));
        assertEquals("png", MimeUtils.guessExtensionFromMimeType("IMAGE/PNG"));
        assertEquals("png", MimeUtils.guessExtensionFromMimeType("IMAGE/png"));
        assertNull(MimeUtils.guessMimeTypeFromExtension(""));
        assertNull(MimeUtils.guessMimeTypeFromExtension("doesnotexist"));
        assertTrue(MimeUtils.hasExtension("PNG"));
        assertTrue(MimeUtils.hasExtension("PnG"));
        assertFalse(MimeUtils.hasExtension(""));
        assertFalse(MimeUtils.hasExtension(".png"));
        assertEquals("image/png", MimeUtils.guessMimeTypeFromExtension("PNG"));
        assertEquals("image/png", MimeUtils.guessMimeTypeFromExtension("PnG"));
        assertNull(MimeUtils.guessMimeTypeFromExtension(".png"));
        assertNull(MimeUtils.guessMimeTypeFromExtension(""));
        assertNull(MimeUtils.guessExtensionFromMimeType("doesnotexist"));
    }

    public void test_30793548() {
        assertEquals("video/3gpp", MimeUtils.guessMimeTypeFromExtension("3gpp"));
        assertEquals("video/3gpp", MimeUtils.guessMimeTypeFromExtension("3gp"));
        assertEquals("video/3gpp2", MimeUtils.guessMimeTypeFromExtension("3gpp2"));
        assertEquals("video/3gpp2", MimeUtils.guessMimeTypeFromExtension("3g2"));
    }

    public void test_37167977() {
        // https://tools.ietf.org/html/rfc5334#section-10.1
        assertEquals("audio/ogg", MimeUtils.guessMimeTypeFromExtension("ogg"));
        assertEquals("audio/ogg", MimeUtils.guessMimeTypeFromExtension("oga"));
        assertEquals("audio/ogg", MimeUtils.guessMimeTypeFromExtension("spx"));
        assertEquals("video/ogg", MimeUtils.guessMimeTypeFromExtension("ogv"));
    }

    public void test_70851634_mimeTypeFromExtension() {
        assertEquals("video/vnd.youtube.yt", MimeUtils.guessMimeTypeFromExtension("yt"));
    }

    public void test_70851634_extensionFromMimeType() {
        assertEquals("yt", MimeUtils.guessExtensionFromMimeType("video/vnd.youtube.yt"));
        assertEquals("yt", MimeUtils.guessExtensionFromMimeType("application/vnd.youtube.yt"));
    }

    public void test_112162449_audio() {
        // According to https://en.wikipedia.org/wiki/M3U#Internet_media_types
        // this is a giant mess, so we pick "audio/x-mpegurl" because a similar
        // playlist format uses "audio/x-scpls".
        assertMimeTypeFromExtension("audio/x-mpegurl", "m3u");
        assertMimeTypeFromExtension("audio/x-mpegurl", "m3u8");
        assertExtensionFromMimeType("m3u", "audio/x-mpegurl");

        assertExtensionFromMimeType("m4a", "audio/mp4");
        assertMimeTypeFromExtension("audio/mpeg", "m4a");

        assertBidirectional("audio/aac", "aac");
    }

    public void test_112162449_video() {
        assertBidirectional("video/x-flv", "flv");
        assertBidirectional("video/quicktime", "mov");
        assertBidirectional("video/mpeg", "mpeg");
    }

    public void test_112162449_image() {
        assertBidirectional("image/heif", "heif");
        assertBidirectional("image/heif-sequence", "heifs");
        assertBidirectional("image/heic", "heic");
        assertBidirectional("image/heic-sequence", "heics");
        assertMimeTypeFromExtension("image/heif", "hif");

        assertBidirectional("image/x-adobe-dng", "dng");
        assertBidirectional("image/x-photoshop", "psd");

        assertBidirectional("image/jp2", "jp2");
        assertMimeTypeFromExtension("image/jp2", "jpg2");
    }

    public void test_120135571_audio() {
        assertMimeTypeFromExtension("audio/mpeg", "m4r");
    }

    public void testWifiConfig_xml() {
        assertExtensionFromMimeType("xml", "application/x-wifi-config");
        assertMimeTypeFromExtension("text/xml", "xml");
    }

    // http://b/122734564
    public void testNonLowercaseMimeType() {
        // A mixed-case mimeType that appears in mime.types; we expect guessMimeTypeFromExtension()
        // to return it in lowercase because MimeUtils considers lowercase to be the canonical form.
        String mimeType = "application/vnd.ms-word.document.macroEnabled.12".toLowerCase(Locale.US);
        assertBidirectional(mimeType, "docm");
    }

    // Check that the keys given for lookups in either direction are not case sensitive
    public void testCaseInsensitiveKeys() {
        String mimeType = MimeUtils.guessMimeTypeFromExtension("apk");
        assertNotNull(mimeType);

        assertEquals(mimeType, MimeUtils.guessMimeTypeFromExtension("APK"));
        assertEquals(mimeType, MimeUtils.guessMimeTypeFromExtension("aPk"));

        assertEquals("apk", MimeUtils.guessExtensionFromMimeType(mimeType));
        assertEquals("apk", MimeUtils.guessExtensionFromMimeType(mimeType.toUpperCase(Locale.US)));
        assertEquals("apk", MimeUtils.guessExtensionFromMimeType(mimeType.toLowerCase(Locale.US)));
    }

    public void test_invalid_empty() {
        checkInvalidExtension("");
        checkInvalidMimeType("");
    }

    public void test_invalid_null() {
        checkInvalidExtension(null);
        checkInvalidMimeType(null);
    }

    public void test_invalid() {
        checkInvalidMimeType("invalid mime type");
        checkInvalidExtension("invalid extension");
    }

    private static void checkInvalidExtension(String s) {
        assertFalse(MimeUtils.hasExtension(s));
        assertNull(MimeUtils.guessMimeTypeFromExtension(s));
    }

    private static void checkInvalidMimeType(String s) {
        assertFalse(MimeUtils.hasMimeType(s));
        assertNull(MimeUtils.guessExtensionFromMimeType(s));
    }

    private static void assertMimeTypeFromExtension(String mimeType, String extension) {
        final String actual = MimeUtils.guessMimeTypeFromExtension(extension);
        if (!Objects.equals(mimeType, actual)) {
            fail("Expected " + mimeType + " but was " + actual + " for extension " + extension);
        }
    }

    private static void assertExtensionFromMimeType(String extension, String mimeType) {
        final String actual = MimeUtils.guessExtensionFromMimeType(mimeType);
        if (!Objects.equals(extension, actual)) {
            fail("Expected " + extension + " but was " + actual + " for type " + mimeType);
        }
    }

    private static void assertBidirectional(String mimeType, String extension) {
        assertMimeTypeFromExtension(mimeType, extension);
        assertExtensionFromMimeType(extension, mimeType);
    }
}
