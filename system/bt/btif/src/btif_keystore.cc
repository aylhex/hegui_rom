/******************************************************************************
 *
 *  Copyright 2019 Google, Inc.
 *
 *  Licensed under the Apache License, Version 2.0 (the "License");
 *  you may not use this file except in compliance with the License.
 *  You may obtain a copy of the License at:
 *
 *  http://www.apache.org/licenses/LICENSE-2.0
 *
 *  Unless required by applicable law or agreed to in writing, software
 *  distributed under the License is distributed on an "AS IS" BASIS,
 *  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 *  See the License for the specific language governing permissions and
 *  limitations under the License.
 *
 ******************************************************************************/

#include "btif_keystore.h"

#include <base/files/file_util.h>
#include <base/logging.h>
#include <base/strings/string_number_conversions.h>
#include <base/strings/string_split.h>
#include <base/strings/string_util.h>
#include <base/strings/utf_string_conversions.h>
#include <sys/stat.h>

using namespace keystore;
using namespace bluetooth;

constexpr char kKeyStore[] = "AndroidKeystore";

namespace bluetooth {

BtifKeystore::BtifKeystore(keystore::KeystoreClient* keystore_client)
    : keystore_client_(keystore_client) {}

std::string BtifKeystore::Encrypt(const std::string& data, int32_t flags) {
  std::lock_guard<std::mutex> lock(api_mutex_);
  std::string output;
  if (data.empty()) {
    LOG(ERROR) << __func__ << ": empty data";
    return output;
  }
  if (!keystore_client_->doesKeyExist(kKeyStore)) {
    auto gen_result = GenerateKey(kKeyStore, 0, false);
    if (!gen_result.isOk()) {
      LOG(FATAL) << "EncryptWithAuthentication Failed: generateKey response="
                 << gen_result;
      return output;
    }
  }
  if (!keystore_client_->encryptWithAuthentication(kKeyStore, data, flags,
                                                   &output)) {
    LOG(FATAL) << "EncryptWithAuthentication failed.";
    return output;
  }
  return output;
}

std::string BtifKeystore::Decrypt(const std::string& input) {
  std::lock_guard<std::mutex> lock(api_mutex_);
  if (input.empty()) {
    LOG(ERROR) << __func__ << ": empty input data";
    return "";
  }
  std::string output;
  if (!keystore_client_->decryptWithAuthentication(kKeyStore, input, &output)) {
    LOG(FATAL) << "DecryptWithAuthentication failed.\n";
  }
  return output;
}

// Note: auth_bound keys created with this tool will not be usable.
KeyStoreNativeReturnCode BtifKeystore::GenerateKey(const std::string& name,
                                                   int32_t flags,
                                                   bool auth_bound) {
  AuthorizationSetBuilder params;
  params.RsaSigningKey(2048, 65537)
      .Digest(Digest::SHA_2_224)
      .Digest(Digest::SHA_2_256)
      .Digest(Digest::SHA_2_384)
      .Digest(Digest::SHA_2_512)
      .Padding(PaddingMode::RSA_PKCS1_1_5_SIGN)
      .Padding(PaddingMode::RSA_PSS);
  if (auth_bound) {
    // Gatekeeper normally generates the secure user id.
    // Using zero allows the key to be created, but it will not be usuable.
    params.Authorization(TAG_USER_SECURE_ID, 0);
  } else {
    params.Authorization(TAG_NO_AUTH_REQUIRED);
  }
  AuthorizationSet hardware_enforced_characteristics;
  AuthorizationSet software_enforced_characteristics;
  return keystore_client_->generateKey(name, params, flags,
                                       &hardware_enforced_characteristics,
                                       &software_enforced_characteristics);
}

bool BtifKeystore::DoesKeyExist() {
  return keystore_client_->doesKeyExist(kKeyStore);
}

}  // namespace bluetooth
