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

package libcore.libcore.net.http;

import java.nio.charset.StandardCharsets;
import java.nio.charset.UnsupportedCharsetException;
import junit.framework.TestCase;
import static libcore.net.http.ResponseUtils.responseCharset;

public class ResponseUtilsTest extends TestCase {
  public void test_responseCharset_missing() {
    assertEquals(StandardCharsets.UTF_8, responseCharset(null));
    assertEquals(StandardCharsets.UTF_8, responseCharset("text/plain"));
    assertEquals(StandardCharsets.UTF_8, responseCharset("text/plain;foo=bar;baz=bal"));
    assertEquals(StandardCharsets.UTF_8, responseCharset("text/plain;charset="));
  }

  public void test_responseCharset_valid() {
    assertEquals(StandardCharsets.ISO_8859_1,
            responseCharset("text/plain;charset=ISO-8859-1"));
    assertEquals(StandardCharsets.ISO_8859_1,
            responseCharset("text/plain;CHARSET=ISO-8859-1"));
    assertEquals(StandardCharsets.ISO_8859_1,
            responseCharset("text/plain;   charset  =   ISO-8859-1"));
    assertEquals(StandardCharsets.ISO_8859_1,
            responseCharset("text/plain; foo=bar;baz=bag;charset=ISO-8859-1"));
    assertEquals(StandardCharsets.ISO_8859_1,
            responseCharset("text/plain;charset=ISO-8859-1;;==,=="));
  }

  public void test_responseCharset_invalid() {
    try {
      responseCharset("text/plain;charset=unsupportedCharset");
      fail();
    } catch (UnsupportedCharsetException expected) {
    }
  }
}
