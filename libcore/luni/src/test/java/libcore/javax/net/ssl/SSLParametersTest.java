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

package libcore.javax.net.ssl;

import java.util.Arrays;
import javax.net.ssl.SSLParameters;
import junit.framework.TestCase;

public class SSLParametersTest extends TestCase {

  public void test_applicationProtocols() {
    SSLParameters params = new SSLParameters();
    try {
      params.setApplicationProtocols(null);
      fail();
    } catch (IllegalArgumentException expected) {
    }
    try {
      params.setApplicationProtocols(new String[] {""});
      fail();
    } catch (IllegalArgumentException expected) {
    }
    try {
      params.setApplicationProtocols(new String[] {null});
      fail();
    } catch (IllegalArgumentException expected) {
    }
    try {
      params.setApplicationProtocols(new String[] {"h2", ""});
      fail();
    } catch (IllegalArgumentException expected) {
    }
    try {
      params.setApplicationProtocols(new String[] {"h2", null});
      fail();
    } catch (IllegalArgumentException expected) {
    }

    // Test that both setApplicationProtocols and getApplicationProtocols clone arrays properly
    String[] protocols = new String[] {"h2"};
    params.setApplicationProtocols(protocols);
    assertTrue(Arrays.equals(new String[] {"h2"}, params.getApplicationProtocols()));
    protocols[0] = "bad";
    assertTrue(Arrays.equals(new String[] {"h2"}, params.getApplicationProtocols()));
    protocols = params.getApplicationProtocols();
    protocols[0] = "bad";
    assertTrue(Arrays.equals(new String[] {"h2"}, params.getApplicationProtocols()));
  }

}
