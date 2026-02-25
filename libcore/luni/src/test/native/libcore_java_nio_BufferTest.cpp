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

#include <jni.h>
#include <nativehelper/JNIHelp.h>

extern "C" jlong Java_libcore_java_nio_BufferTest_jniGetDirectBufferAddress(
    JNIEnv* env, jobject /* clazz */, jobject buffer) {
  return reinterpret_cast<jlong>(env->GetDirectBufferAddress(buffer));
}

extern "C" jlong Java_libcore_java_nio_BufferTest_jniGetDirectBufferCapacity(
    JNIEnv* env, jobject /* clazz */, jobject buffer) {
  return reinterpret_cast<jlong>(env->GetDirectBufferCapacity(buffer));
}

extern "C" jobject Java_libcore_java_nio_BufferTest_jniNewDirectByteBuffer(
    JNIEnv* env, jobject /* clazz */) {
  // We use (nullptr, 0) here because a DirectByteBuffer is allowed to wrap
  // nullptr providing the buffer is zero length.
  return env->NewDirectByteBuffer(nullptr, 0);
}
