/*
 * Copyright (C) 2013 The Android Open Source Project
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

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.RandomAccessFile;

import libcore.timezone.TimeZoneDataFiles;
import libcore.timezone.testing.ZoneInfoTestHelper;
import libcore.util.ZoneInfo;
import libcore.timezone.ZoneInfoDB;

import static libcore.timezone.ZoneInfoDB.TzData.SIZEOF_INDEX_ENTRY;

public class ZoneInfoDBTest extends junit.framework.TestCase {

  // The base tzdata file, always present on a device.
  private static final String SYSTEM_TZDATA_FILE =
      TimeZoneDataFiles.getSystemTimeZoneFile(ZoneInfoDB.TZDATA_FILE);

  // An empty override file should fall back to the default file.
  public void testLoadTzDataWithFallback_emptyOverrideFile() throws Exception {
    String emptyFilePath = makeEmptyFile().getPath();
    try (ZoneInfoDB.TzData data = ZoneInfoDB.TzData.loadTzData(SYSTEM_TZDATA_FILE);
         ZoneInfoDB.TzData dataWithEmptyOverride =
                 ZoneInfoDB.TzData.loadTzDataWithFallback(emptyFilePath, SYSTEM_TZDATA_FILE)) {
      assertEquals(data.getVersion(), dataWithEmptyOverride.getVersion());
      assertEquals(data.getAvailableIDs().length, dataWithEmptyOverride.getAvailableIDs().length);
    }
  }

  // A corrupt override file should fall back to the default file.
  public void testLoadTzDataWithFallback_corruptOverrideFile() throws Exception {
    String corruptFilePath = makeCorruptFile().getPath();
    try (ZoneInfoDB.TzData data = ZoneInfoDB.TzData.loadTzData(SYSTEM_TZDATA_FILE);
         ZoneInfoDB.TzData dataWithCorruptOverride =
                 ZoneInfoDB.TzData.loadTzDataWithFallback(corruptFilePath, SYSTEM_TZDATA_FILE)) {
      assertEquals(data.getVersion(), dataWithCorruptOverride.getVersion());
      assertEquals(data.getAvailableIDs().length, dataWithCorruptOverride.getAvailableIDs().length);
    }
  }

  // Given no tzdata files we can use, we should fall back to built-in "GMT".
  public void testLoadTzDataWithFallback_noGoodFile() throws Exception {
    String emptyFilePath = makeEmptyFile().getPath();
    try (ZoneInfoDB.TzData data = ZoneInfoDB.TzData.loadTzDataWithFallback(emptyFilePath)) {
      assertEquals("missing", data.getVersion());
      assertEquals(1, data.getAvailableIDs().length);
      assertEquals("GMT", data.getAvailableIDs()[0]);
    }
  }

  // Given a valid override file, we should find ourselves using that.
  public void testLoadTzDataWithFallback_goodOverrideFile() throws Exception {
    RandomAccessFile in = new RandomAccessFile(SYSTEM_TZDATA_FILE, "r");
    byte[] content = new byte[(int) in.length()];
    in.readFully(content);
    in.close();

    // Bump the version number to one long past where humans will be extinct.
    content[6] = '9';
    content[7] = '9';
    content[8] = '9';
    content[9] = '9';
    content[10] = 'z';

    File goodFile = makeTemporaryFile(content);
    try (ZoneInfoDB.TzData dataWithOverride =
              ZoneInfoDB.TzData.loadTzDataWithFallback(goodFile.getPath(), SYSTEM_TZDATA_FILE);
         ZoneInfoDB.TzData data = ZoneInfoDB.TzData.loadTzData(SYSTEM_TZDATA_FILE)) {

      assertEquals("9999z", dataWithOverride.getVersion());
      assertEquals(data.getAvailableIDs().length, dataWithOverride.getAvailableIDs().length);
    } finally {
      goodFile.delete();
    }
  }

  public void testLoadTzData_badHeader() throws Exception {
    RandomAccessFile in = new RandomAccessFile(SYSTEM_TZDATA_FILE, "r");
    byte[] content = new byte[(int) in.length()];
    in.readFully(content);
    in.close();

    // Break the header.
    content[0] = 'a';
    checkInvalidDataDetected(content);
  }

  public void testLoadTzData_validTestData() throws Exception {
    byte[] data = new ZoneInfoTestHelper.TzDataBuilder().initializeToValid().build();
    File testFile = makeTemporaryFile(data);
    try {
      assertNotNull(ZoneInfoDB.TzData.loadTzData(testFile.getPath()));
    } finally {
      testFile.delete();
    }
  }

  public void testLoadTzData_invalidOffsets() throws Exception {
    ZoneInfoTestHelper.TzDataBuilder builder =
            new ZoneInfoTestHelper.TzDataBuilder().initializeToValid();

    // Sections must be in the correct order: section sizing is calculated using them.
    builder.setIndexOffsetOverride(10);
    builder.setDataOffsetOverride(30);

    byte[] data = builder.build();
    // The offsets must all be under the total size of the file for this test to be valid.
    assertTrue(30 < data.length);
    checkInvalidDataDetected(data);
  }

  public void testLoadTzData_zoneTabOutsideFile() throws Exception {
    ZoneInfoTestHelper.TzDataBuilder builder =
            new ZoneInfoTestHelper.TzDataBuilder()
                    .initializeToValid();

    // Sections must be in the correct order: section sizing is calculated using them.
    builder.setIndexOffsetOverride(10);
    builder.setDataOffsetOverride(10 + SIZEOF_INDEX_ENTRY);
    builder.setZoneTabOffsetOverride(3000); // This is invalid if it is outside of the file.

    byte[] data = builder.build();
    // The zoneTab offset must be outside of the file for this test to be valid.
    assertTrue(3000 > data.length);
    checkInvalidDataDetected(data);
  }

  public void testLoadTzData_nonDivisibleIndex() throws Exception {
    ZoneInfoTestHelper.TzDataBuilder builder =
            new ZoneInfoTestHelper.TzDataBuilder().initializeToValid();

    // Sections must be in the correct order: section sizing is calculated using them.
    int indexOffset = 10;
    builder.setIndexOffsetOverride(indexOffset);
    int dataOffset = indexOffset + ZoneInfoDB.TzData.SIZEOF_INDEX_ENTRY - 1;
    builder.setDataOffsetOverride(dataOffset);
    builder.setZoneTabOffsetOverride(dataOffset + 40);

    byte[] data = builder.build();
    // The zoneTab offset must be outside of the file for this test to be valid.
    assertTrue(3000 > data.length);
    checkInvalidDataDetected(data);
  }

  public void testLoadTzData_badId() throws Exception {
    ZoneInfoTestHelper.TzDataBuilder builder =
            new ZoneInfoTestHelper.TzDataBuilder().initializeToValid();
    builder.clearZicData();
    byte[] validZicData =
            new ZoneInfoTestHelper.ZicDataBuilder().initializeToValid().build();
    builder.addZicData("", validZicData); // "" is an invalid ID

    checkInvalidDataDetected(builder.build());
  }

  public void testLoadTzData_badIdOrder() throws Exception {
    ZoneInfoTestHelper.TzDataBuilder builder =
            new ZoneInfoTestHelper.TzDataBuilder().initializeToValid();
    builder.clearZicData();
    byte[] validZicData =
            new ZoneInfoTestHelper.ZicDataBuilder().initializeToValid().build();
    builder.addZicData("Europe/Zurich", validZicData);
    builder.addZicData("Europe/London", validZicData);

    checkInvalidDataDetected(builder.build());
  }

  public void testLoadTzData_duplicateId() throws Exception {
    ZoneInfoTestHelper.TzDataBuilder builder =
            new ZoneInfoTestHelper.TzDataBuilder().initializeToValid();
    builder.clearZicData();
    byte[] validZicData =
            new ZoneInfoTestHelper.ZicDataBuilder().initializeToValid().build();
    builder.addZicData("Europe/London", validZicData);
    builder.addZicData("Europe/London", validZicData);

    checkInvalidDataDetected(builder.build());
  }

  public void testLoadTzData_badZicLength() throws Exception {
    ZoneInfoTestHelper.TzDataBuilder builder =
            new ZoneInfoTestHelper.TzDataBuilder().initializeToValid();
    builder.clearZicData();
    byte[] invalidZicData = "This is too short".getBytes();
    builder.addZicData("Europe/London", invalidZicData);

    checkInvalidDataDetected(builder.build());
  }

  private static void checkInvalidDataDetected(byte[] data) throws Exception {
    File testFile = makeTemporaryFile(data);
    try {
      assertNull(ZoneInfoDB.TzData.loadTzData(testFile.getPath()));
    } finally {
      testFile.delete();
    }
  }

  // Confirms any caching that exists correctly handles TimeZone mutability.
  public void testMakeTimeZone_timeZoneMutability() throws Exception {
    try (ZoneInfoDB.TzData data = ZoneInfoDB.TzData.loadTzData(SYSTEM_TZDATA_FILE)) {
      String tzId = "Europe/London";
      ZoneInfo first = data.makeTimeZone(tzId);
      ZoneInfo second = data.makeTimeZone(tzId);
      assertNotSame(first, second);

      assertTrue(first.hasSameRules(second));

      first.setID("Not Europe/London");

      assertFalse(first.getID().equals(second.getID()));

      first.setRawOffset(3600);
      assertFalse(first.getRawOffset() == second.getRawOffset());
    }
  }

  public void testMakeTimeZone_notFound() throws Exception {
    try (ZoneInfoDB.TzData data = ZoneInfoDB.TzData.loadTzData(SYSTEM_TZDATA_FILE)) {
      assertNull(data.makeTimeZone("THIS_TZ_DOES_NOT_EXIST"));
      assertFalse(data.hasTimeZone("THIS_TZ_DOES_NOT_EXIST"));
    }
  }

  public void testMakeTimeZone_found() throws Exception {
    try (ZoneInfoDB.TzData data = ZoneInfoDB.TzData.loadTzData(SYSTEM_TZDATA_FILE)) {
      assertNotNull(data.makeTimeZone("Europe/London"));
      assertTrue(data.hasTimeZone("Europe/London"));
    }
  }

  private static File makeCorruptFile() throws Exception {
    return makeTemporaryFile("invalid content".getBytes());
  }

  private static File makeEmptyFile() throws Exception {
    return makeTemporaryFile(new byte[0]);
  }

  private static File makeTemporaryFile(byte[] content) throws Exception {
    File f = File.createTempFile("temp-", ".txt");
    FileOutputStream fos = new FileOutputStream(f);
    fos.write(content);
    fos.close();
    return f;
  }
}
