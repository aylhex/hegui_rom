/*
 * Copyright (C) 2015 The Android Open Source Project
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
 * limitations under the License
 */

package libcore.java.nio.charset;

import junit.framework.TestCase;

import java.io.UTFDataFormatException;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.charset.ModifiedUtf8;
import java.util.Arrays;

/**
 * Tests for {@code ModifiedUtf8}.
 */
public class ModifiedUtf8Test extends TestCase {
    public void test_decode_singleChar() throws Exception {
        assertEquals("A", ModifiedUtf8.decode(new byte[] { 'A' }, new char[1], 0, 1));
    }

    public void test_decode_checkOffsetAndLength() throws Exception {
        assertEquals("BC", ModifiedUtf8.decode(
                new byte[] { 'A', 'B', 'C', 'D' }, new char[2], 1, 2));
    }

    public void test_decode_unexpectedEndOfStreamAfterC2_throws() {
        // We need at least one byte after 0xc2.
        try {
            ModifiedUtf8.decode(new byte[]{'B', (byte) 0xc2}, new char[2], 0, 2);
            fail("Should throw " + UTFDataFormatException.class.getName());
        } catch(UTFDataFormatException expected) {
            // Expected.
        }
    }

    public void test_decode_unexpectedEndOfStreamAfterE0_throws() {
        // We need at least two bytes after 0xe0.
        try {
            ModifiedUtf8.decode(
                    new byte[] { 'B', (byte) 0xe0, (byte) 0xab }, new char[2], 0, 3);
            fail("Should throw " + UTFDataFormatException.class.getName());
        } catch(UTFDataFormatException expected) {
            // Expected.
        }
    }

    public void test_decode_endOfStreamAfterC2() throws Exception {
        assertEquals("B\u00a0", ModifiedUtf8.decode(
                new byte[] { 'B', (byte) 0xc2, (byte) 0xa0 },
                new char[2],
                0,
                3));
    }

    public void test_decode_endOfStreamAfterE0() throws Exception {
        assertEquals("B\u0830", ModifiedUtf8.decode(
                new byte[] { 'B', (byte) 0xe0, (byte) 0xa0, (byte) 0xb0 },
                new char[2],
                0,
                4));
    }

    public void test_decode_invalidByte_characterUnknown() throws Exception {
        try {
            ModifiedUtf8.decode(new byte[]{'A', (byte) 0xf0}, new char[2], 0, 2);
            fail("Should throw " + UTFDataFormatException.class.getName());
        } catch (UTFDataFormatException expected) {
            // Expected.
        }
    }

    public void test_decode_someC2Character() throws Exception {
        assertEquals("A\u00a6", ModifiedUtf8.decode(
                new byte[] { 'A', (byte) 0xc2, (byte) 0xa6 }, new char[2], 0, 3));
    }

    public void test_decode_lastC2Character() throws Exception {
        assertEquals("A\u00bf", ModifiedUtf8.decode(
                new byte[] { 'A', (byte) 0xc2, (byte) 0xbf }, new char[2], 0, 3));
    }

    public void test_decode_someTwoByteCharacter() throws Exception {
        // Make sure bit masking works
        assertEquals("A\u0606", ModifiedUtf8.decode(
                new byte[] { 'A', (byte) 0xd8, (byte) 0x86 }, new char[3], 0, 3));
    }

    public void test_decode_lastTwoByteCharacter() throws Exception {
        assertEquals("A\u07ff", ModifiedUtf8.decode(
                new byte[] { 'A', (byte) 0xdf, (byte) 0xbf }, new char[2], 0, 3));
    }

    public void test_decode_firstE0Character() throws Exception {
        assertEquals("A\u0800", ModifiedUtf8.decode(
                new byte[] { 'A', (byte) 0xe0, (byte) 0xa0, (byte) 0x80 },
                new char[2],
                0,
                4));
    }

    public void test_decode_someThreeBytesCharacter() throws Exception {
        assertEquals("A\u31c6", ModifiedUtf8.decode(
                new byte[]{ 'A', (byte) 0xe3, (byte) 0x87, (byte) 0x86 },
                new char[2],
                0,
                4));
    }

    public void test_decode_lastThreeBytesCharacter() throws Exception {
        assertEquals("A\uffff", ModifiedUtf8.decode(
                new byte[] { 'A', (byte) 0xef, (byte) 0xbf, (byte) 0xbf },
                new char[2],
                0,
                4));
    }

    public void test_decode_twoByteCharacterAfterThreeByteCharacter() throws Exception {
        assertEquals("\uffff\u0606A", ModifiedUtf8.decode(
                new byte[] { (byte) 0xef, (byte) 0xbf, (byte) 0xbf, (byte) 0xd8, (byte) 0x86, 'A' },
                new char[3],
                0,
                6));
    }

    public void test_decode_c080isZero() throws Exception {
        assertEquals("A\u0000A", ModifiedUtf8.decode(
                new byte[] { 'A', (byte) 0xc0, (byte) 0x80, 'A' }, new char[3], 0, 4));
    }

    public void test_decode_00isZero() throws Exception {
        assertEquals("A\u0000A", ModifiedUtf8.decode(
                new byte[] { 'A', (byte) 0, 'A' }, new char[3], 0, 3));
    }

    public void test_decode_insufficientOutputSpace_throws() throws Exception{
        try {
            ModifiedUtf8.decode(new byte[] { 'A', (byte) 0, 'A' }, new char[2], 0,  3);
            fail("Should throw " + ArrayIndexOutOfBoundsException.class.getName());
        } catch(ArrayIndexOutOfBoundsException expected) {
            // Expected.
        }
    }

    public void test_decode_checkBadSecondByteOfTwo() throws Exception {
        try {
            ModifiedUtf8.decode(new byte[]{(byte) 0xc0, (byte) 0xc0}, new char[2], 0, 2);
            fail("Should throw " + UTFDataFormatException.class.getName());
        } catch (UTFDataFormatException expected) {
            // Expected.
        }
    }

    public void test_decode_checkBadSecondByteOfThree() throws Exception{
        try {
            ModifiedUtf8.decode(new byte[]{
                    (byte) 0xe0, (byte) 0xc0, (byte) 0x80}, new char[2], 0, 2);
            fail("Should throw " + UTFDataFormatException.class.getName());
        } catch (UTFDataFormatException expected) {
            // Expected.
        }
    }

    public void test_decode_checkBadThirdByteOfThree() throws Exception{
        try {
            ModifiedUtf8.decode(new byte[]{
                    (byte) 0xe0, (byte) 0x80, (byte) 0xc0}, new char[2], 0, 2);
            fail("Should throw " + UTFDataFormatException.class.getName());
        } catch (UTFDataFormatException expected) {
            // Expected.
        }
    }

    public void test_decode_insufficientInput_throws() throws Exception{
        try {
            ModifiedUtf8.decode(new byte[] { 'A', (byte) 0, 'A' }, new char[8], 0,  100);
            fail("Should throw " + ArrayIndexOutOfBoundsException.class.getName());
        } catch(ArrayIndexOutOfBoundsException expected) {
            // Expected.
        }
    }

    public void test_decode_extraCharsInArray_ignored() throws Exception {
        assertEquals("A", ModifiedUtf8.decode(new byte[] { 'A' }, new char[] { 'B', 'Z' }, 0,  1));
    }

    public void test_countBytes_rightCount() throws Exception {
        assertEquals(0, ModifiedUtf8.countBytes("", false));
        assertEquals(2, ModifiedUtf8.countBytes("\u0000", false));
        assertEquals(1, ModifiedUtf8.countBytes("A", false));
        assertEquals(1, ModifiedUtf8.countBytes("\u007f", false));
        assertEquals(2, ModifiedUtf8.countBytes("\u0080", false));
        assertEquals(2, ModifiedUtf8.countBytes("\u07ff", false));
        assertEquals(3, ModifiedUtf8.countBytes("\u0800", false));
        assertEquals(3, ModifiedUtf8.countBytes("\uffff", false));
    }

    public void test_countBytes_checkExceptionThrown() throws Exception {
        // These two mustn't throw...
        ModifiedUtf8.countBytes("", true);
        ModifiedUtf8.countBytes("A", true);

        char[] unsignedShortSizedCharArray = new char[2 * Short.MAX_VALUE + 1];
        for (int i = 0; i < unsignedShortSizedCharArray.length; i++) {
            unsignedShortSizedCharArray[i] = 'A';
        }
        String unsignedShortSizedString = String.copyValueOf(unsignedShortSizedCharArray);

        char[] sizeLongerThanUnsignedShortCharArray = new char[2 * Short.MAX_VALUE + 2];
        for (int i = 0; i < sizeLongerThanUnsignedShortCharArray.length; i++) {
            sizeLongerThanUnsignedShortCharArray[i] = 'A';
        }
        String sizeLongerThanUnsignedShortString = String.copyValueOf(
                sizeLongerThanUnsignedShortCharArray);

        // Mustn't throw.
        ModifiedUtf8.countBytes(unsignedShortSizedString, true);

        try {
            // Must throw.
            ModifiedUtf8.countBytes(sizeLongerThanUnsignedShortString, true);
            fail();
        } catch (UTFDataFormatException expected) {
            // Expected.
        }

        // Mustn't throw.
        ModifiedUtf8.countBytes(unsignedShortSizedString, false);
        ModifiedUtf8.countBytes(sizeLongerThanUnsignedShortString, false);
    }

    public void test_encode() throws Exception {
        assertTrue(Arrays.equals(new byte[]{0, 1, 'A'}, ModifiedUtf8.encode("A")));
        assertTrue(Arrays.equals(new byte[] { 0, 3, 'A', 'B', 'C' }, ModifiedUtf8.encode("ABC")));
        assertTrue(Arrays.equals(new byte[] { 0, 3, 'A', (byte) 0xc2, (byte) 0xa0 },
                ModifiedUtf8.encode("A\u00a0")));
        assertTrue(Arrays.equals(new byte[] { 0, 4, 'A', (byte) 0xe0, (byte) 0xa0, (byte) 0xb0 },
                ModifiedUtf8.encode("A\u0830")));
        assertTrue(Arrays.equals(new byte[] { 0, 3, 'A', (byte) 0xc2, (byte) 0xa6 },
                ModifiedUtf8.encode("A\u00a6")));
        assertTrue(Arrays.equals(new byte[] { 0, 3, 'A', (byte) 0xc2, (byte) 0xbf },
                ModifiedUtf8.encode("A\u00bf")));
        assertTrue(Arrays.equals(new byte[] { 0, 3, 'A', (byte) 0xd8, (byte) 0x86 },
                ModifiedUtf8.encode("A\u0606")));
        assertTrue(Arrays.equals(new byte[] { 0, 3, 'A', (byte) 0xdf, (byte) 0xbf },
                ModifiedUtf8.encode("A\u07ff")));
        assertTrue(Arrays.equals(new byte[] { 0, 4, 'A', (byte) 0xe0, (byte) 0xa0, (byte) 0x80 },
                ModifiedUtf8.encode("A\u0800")));
        assertTrue(Arrays.equals(new byte[] { 0, 4, 'A', (byte) 0xe3, (byte) 0x87, (byte) 0x86 },
                ModifiedUtf8.encode("A\u31c6")));
        assertTrue(Arrays.equals(new byte[] { 0, 4, 'A', (byte) 0xef, (byte) 0xbf, (byte) 0xbf },
                ModifiedUtf8.encode("A\uffff")));
        assertTrue(Arrays.equals(new byte[] { 0, 3, 'A', (byte) 0xc0, (byte) 0x80 },
                ModifiedUtf8.encode("A\u0000")));
        assertTrue(
                Arrays.equals(new byte[] { 0, 8, (byte) 0xe3, (byte) 0x87, (byte) 0x86,
                                (byte) 0xd8, (byte) 0x86, (byte) 0xc0, (byte) 0x80, 'A' },
                ModifiedUtf8.encode("\u31c6\u0606\u0000A")));
    }

    public void test_encode_throws() throws Exception {
        char[] unsignedShortSizedCharArray = new char[Short.MAX_VALUE * 2 + 1];
        for (int i = 0; i < unsignedShortSizedCharArray.length; i++) {
            unsignedShortSizedCharArray[i] = 'A';
        }
        String unsignedShortSizedString = String.copyValueOf(unsignedShortSizedCharArray);

        char[] sizeLongerThanUnsignedShortCharArray = new char[Short.MAX_VALUE * 2 + 2];
        for (int i = 0; i < sizeLongerThanUnsignedShortCharArray.length; i++) {
            sizeLongerThanUnsignedShortCharArray[i] = 'A';
        }
        String sizeLongerThanUnsignedShortString =
                String.copyValueOf(sizeLongerThanUnsignedShortCharArray);

        // Mustn't throw.
        ModifiedUtf8.encode(unsignedShortSizedString);
        try {
            // Must throw.
            ModifiedUtf8.encode(sizeLongerThanUnsignedShortString);
            fail("Should throw " + UTFDataFormatException.class.getName());
        } catch (UTFDataFormatException expected) {
            // Expected.
        }
    }

    public void test_encode_lengthAtBeginning() throws Exception {
        int testStringLength = 20000;
        char[] charArray = new char[testStringLength];
        for (int i = 0; i < charArray.length; i++) {
            charArray[i] = 'A';
        }
        String testString = String.copyValueOf(charArray);

        // Mustn't throw.
        byte[] result = ModifiedUtf8.encode(testString);
        ByteBuffer b = ByteBuffer.wrap(result);
        b.order(ByteOrder.BIG_ENDIAN);
        assertEquals(testStringLength, b.getShort());
    }

}
