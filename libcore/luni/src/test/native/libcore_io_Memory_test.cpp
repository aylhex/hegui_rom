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

#include "luni/src/main/native/libcore_io_Memory.cpp"

#include <stdlib.h>

#include <functional>

#include <gtest/gtest.h>

#define ALIGNMENT 8

template<typename T, size_t NUM_ELEMENTS>
void swap_align_test(void (*swap_func)(T*, const T*, size_t),
                     std::function<void (T*, T*, uint64_t)> init_func) {
  uint8_t* dst = nullptr;
  uint8_t* src = nullptr;
  ASSERT_EQ(0, posix_memalign(reinterpret_cast<void**>(&dst), ALIGNMENT,
                              sizeof(T) * NUM_ELEMENTS + ALIGNMENT));
  ASSERT_EQ(0, posix_memalign(reinterpret_cast<void**>(&src), ALIGNMENT,
                              sizeof(T) * NUM_ELEMENTS + ALIGNMENT));

  T src_buf[NUM_ELEMENTS];
  T dst_buf[NUM_ELEMENTS];
  for (uint64_t i = 0; i < NUM_ELEMENTS; i++) {
    init_func(&src_buf[i], &dst_buf[i], i);
  }

  // Vary a few alignments.
  for (size_t dst_align = 0; dst_align < ALIGNMENT; dst_align++) {
    T* dst_aligned = reinterpret_cast<T*>(&dst[dst_align]);
    for (size_t src_align = 0; src_align < ALIGNMENT; src_align++) {
      T* src_aligned = reinterpret_cast<T*>(&src[src_align]);
      memset(dst_aligned, 0, sizeof(T) * NUM_ELEMENTS);
      memcpy(src_aligned, src_buf, sizeof(T) * NUM_ELEMENTS);
      swap_func(dst_aligned, src_aligned, NUM_ELEMENTS);
      ASSERT_EQ(0, memcmp(dst_buf, dst_aligned, sizeof(T) * NUM_ELEMENTS))
          << "Failed at dst align " << dst_align << " src align " << src_align;
    }
  }
  free(dst);
  free(src);
}

TEST(libcore, swapShorts_align_test) {
  // Use an odd number to guarantee that the last 16-bit swap code
  // is executed.
  swap_align_test<jshort, 9> (swapShorts, [] (jshort* src, jshort* dst, uint64_t i) {
    *src = ((2*i) << 8) | (2*(i+1));
    *dst = (2*i) | ((2*(i+1)) << 8);
  });
}

TEST(libcore, swapInts_align_test) {
  swap_align_test<jint, 10> (swapInts, [] (jint* src, jint* dst, uint64_t i) {
    *src = ((4*i) << 24) | ((4*(i+1)) << 16) | ((4*(i+2)) << 8) | (4*(i+3));
    *dst = (4*i) | ((4*(i+1)) << 8) | ((4*(i+2)) << 16) | ((4*(i+3)) << 24);
  });
}

TEST(libcore, swapLongs_align_test) {
  swap_align_test<jlong, 10> (swapLongs, [] (jlong* src, jlong* dst, uint64_t i) {
    *src = ((8*i) << 56) | ((8*(i+1)) << 48) | ((8*(i+2)) << 40) | ((8*(i+3)) << 32) |
        ((8*(i+4)) << 24) | ((8*(i+5)) << 16) | ((8*(i+6)) << 8) | (8*(i+7));
    *dst = (8*i) | ((8*(i+1)) << 8) | ((8*(i+2)) << 16) | ((8*(i+3)) << 24) |
        ((8*(i+4)) << 32) | ((8*(i+5)) << 40) | ((8*(i+6)) << 48) | ((8*(i+7)) << 56);
  });
}

template<typename T>
void memory_peek_test(T (*peek_func)(JNIEnv*, jclass, jlong), T value) {
  T* src = nullptr;
  ASSERT_EQ(0, posix_memalign(reinterpret_cast<void**>(&src), ALIGNMENT,
                              sizeof(T) + ALIGNMENT));
  for (size_t i = 0; i < ALIGNMENT; i++) {
    jlong src_aligned = reinterpret_cast<jlong>(src) + i;
    memcpy(reinterpret_cast<void*>(src_aligned), &value, sizeof(T));
    T result = peek_func(nullptr, nullptr, src_aligned);
    ASSERT_EQ(value, result);
  }
  free(src);
}

TEST(libcore, Memory_peekShortNative_align_check) {
  memory_peek_test<jshort>(Memory_peekShortNative, 0x0102);
}

TEST(libcore, Memory_peekIntNative_align_check) {
  memory_peek_test<jint>(Memory_peekIntNative, 0x01020304);
}

TEST(libcore, Memory_peekLongNative_align_check) {
  memory_peek_test<jlong>(Memory_peekLongNative, 0x01020405060708ULL);
}

template<typename T>
void memory_poke_test(void (*poke_func)(JNIEnv*, jclass, jlong, T), T value) {
  T* dst = nullptr;
  ASSERT_EQ(0, posix_memalign(reinterpret_cast<void**>(&dst), ALIGNMENT,
                              sizeof(T) + ALIGNMENT));
  for(size_t i = 0; i < ALIGNMENT; i++) {
    memset(dst, 0, sizeof(T) + ALIGNMENT);
    jlong dst_aligned = reinterpret_cast<jlong>(dst) + i;
    poke_func(nullptr, nullptr, dst_aligned, value);
    ASSERT_EQ(0, memcmp(reinterpret_cast<void*>(dst_aligned), &value, sizeof(T)));
  }
  free(dst);
}

TEST(libcore, Memory_pokeShortNative_align_check) {
  memory_poke_test<jshort>(Memory_pokeShortNative, 0x0102);
}

TEST(libcore, Memory_pokeIntNative_align_check) {
  memory_poke_test<jint>(Memory_pokeIntNative, 0x01020304);
}

TEST(libcore, Memory_pokeLongNative_align_check) {
  memory_poke_test<jlong>(Memory_pokeLongNative, 0x0102030405060708ULL);
}
