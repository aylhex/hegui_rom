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
 * limitations under the License.
 */

#include <memory>
#include <string>

#include <pthread.h>
#include <sys/prctl.h>

#include <jni.h>
#include <nativehelper/JNIHelp.h>

static JavaVM* javaVm = nullptr;

static void* TestThreadNaming(void* arg) {
    const bool attach_with_name = (reinterpret_cast<uint64_t>(arg) == 1);
    const std::string native_thread_name = "foozball";
    pthread_setname_np(pthread_self(), native_thread_name.c_str());

    JNIEnv* env;
    JavaVMAttachArgs args;
    args.version = JNI_VERSION_1_6;
    args.group = nullptr;
    if (attach_with_name) {
        args.name = native_thread_name.c_str();
    } else {
        args.name = nullptr;
    }

    if (javaVm->AttachCurrentThread(&env, &args) != JNI_OK) {
        return new std::string("Attach failed");
    }

    std::string* exception_message = nullptr;
    std::unique_ptr<char[]> thread_name(new char[32]);
    if (prctl(PR_GET_NAME, reinterpret_cast<unsigned long>(thread_name.get()), 0L, 0L, 0L) == 0) {
        // If a thread is attached with a name, the native thread name must be set to
        // the supplied name. In this test, the name we attach with == the
        // native_thread_name.
        if (attach_with_name && (thread_name.get() != native_thread_name)) {
            exception_message = new std::string("expected_thread_name != thread_name: ");
            exception_message->append("expected :");
            exception_message->append(native_thread_name);
            exception_message->append(" was :");
            exception_message->append(thread_name.get());
        }

        // On the other hand, if the thread isn't attached with a name - the
        // runtime assigns a name according to the usual thread naming scheme.
        if (!attach_with_name && strncmp(thread_name.get(), "Thread", 6)) {
            exception_message = new std::string("unexpected thread name : ");
            exception_message->append(thread_name.get());
        }
    } else {
        exception_message = new std::string("prctl(PR_GET_NAME) failed :");
        exception_message->append(strerror(errno));
    }


    if (javaVm->DetachCurrentThread() != JNI_OK) {
        exception_message = new std::string("Detach failed");
    }

    return exception_message;
}

extern "C" jstring Java_libcore_java_lang_ThreadTest_nativeTestNativeThreadNames(
    JNIEnv* env, jobject /* object */) {
  std::string result;

  // TEST 1: Test that a thread attaching with a specified name (in the
  // JavaVMAttachArgs) does not have its name changed.
  pthread_t attacher;
  if (pthread_create(&attacher, nullptr, TestThreadNaming,
                     reinterpret_cast<void*>(static_cast<uint64_t>(0))) != 0) {
      jniThrowException(env, "java/lang/IllegalStateException", "Attach failed");
  }

  std::string* result_test1;
  if (pthread_join(attacher, reinterpret_cast<void**>(&result_test1)) != 0) {
      jniThrowException(env, "java/lang/IllegalStateException", "Join failed");
  }

  if (result_test1 != nullptr) {
      result.append("test 1: ");
      result.append(*result_test1);
  }

  // TEST 2: Test that a thread attaching without a specified name (in the
  // JavaVMAttachArgs) has its native name changed as per the standard naming
  // convention.
  pthread_t attacher2;
  if (pthread_create(&attacher2, nullptr, TestThreadNaming,
                     reinterpret_cast<void*>(static_cast<uint64_t>(1))) != 0) {
      jniThrowException(env, "java/lang/IllegalStateException", "Attach failed");
  }

  std::string* result_test2;
  if (pthread_join(attacher2, reinterpret_cast<void**>(&result_test2)) != 0) {
      jniThrowException(env, "java/lang/IllegalStateException", "Join failed");
  }

  if (result_test2 != nullptr) {
      result.append("test 2: ");
      result.append(*result_test2);
  }

  // Return test results.
  jstring resultJString = nullptr;
  if (result.size() > 0) {
    resultJString = env->NewStringUTF(result.c_str());
  }

  delete result_test1;
  delete result_test2;

  return resultJString;
}

extern "C" int JNI_OnLoad(JavaVM* vm, void*) {
    javaVm = vm;
    return JNI_VERSION_1_6;
}
