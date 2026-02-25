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

// The functions we want to benchmark are static, so include the source code.
#include "luni/src/main/native/libcore_io_Memory.cpp"

#include <benchmark/benchmark.h>

template<typename T, size_t ALIGN>
void swap_bench(benchmark::State& state, void (*swap_func)(T*, const T*, size_t)) {
  size_t num_elements = state.range(0);

  T* src;
  T* dst;
  T* src_elems;
  T* dst_elems;

  if (ALIGN) {
    src_elems = new T[num_elements + 1];
    dst_elems = new T[num_elements + 1];

    src = reinterpret_cast<T*>(reinterpret_cast<uintptr_t>(src_elems) + ALIGN);
    dst = reinterpret_cast<T*>(reinterpret_cast<uintptr_t>(dst_elems) + ALIGN);
  } else {
    src_elems = new T[num_elements];
    dst_elems = new T[num_elements];

    src = src_elems;
    dst = dst_elems;
  }

  memset(dst, 0, sizeof(T) * num_elements);
  memset(src, 0x12, sizeof(T) * num_elements);

  while (state.KeepRunning()) {
    swap_func(src, dst, num_elements);
  }

  delete[] src_elems;
  delete[] dst_elems;
}

#define AT_COMMON_VALUES \
    Arg(10)->Arg(100)->Arg(1000)->Arg(1024*10)->Arg(1024*100)

// Aligned.

static void BM_swapShorts_aligned(benchmark::State& state) {
  swap_bench<jshort, 0>(state, swapShorts);
}
BENCHMARK(BM_swapShorts_aligned)->AT_COMMON_VALUES;

static void BM_swapInts_aligned(benchmark::State& state) {
  swap_bench<jint, 0>(state, swapInts);
}
BENCHMARK(BM_swapInts_aligned)->AT_COMMON_VALUES;

static void BM_swapLongs_aligned(benchmark::State& state) {
  swap_bench<jlong, 0>(state, swapLongs);
}
BENCHMARK(BM_swapLongs_aligned)->AT_COMMON_VALUES;

// Unaligned 1.

static void BM_swapShorts_unaligned_1(benchmark::State& state) {
  swap_bench<jshort, 1>(state, swapShorts);
}
BENCHMARK(BM_swapShorts_unaligned_1)->AT_COMMON_VALUES;

static void BM_swapInts_unaligned_1(benchmark::State& state) {
  swap_bench<jint, 1>(state, swapInts);
}
BENCHMARK(BM_swapInts_unaligned_1)->AT_COMMON_VALUES;

static void BM_swapLongs_unaligned_1(benchmark::State& state) {
  swap_bench<jlong, 1>(state, swapLongs);
}
BENCHMARK(BM_swapLongs_unaligned_1)->AT_COMMON_VALUES;

// Unaligned 2.

static void BM_swapShorts_unaligned_2(benchmark::State& state) {
  swap_bench<jshort, 2>(state, swapShorts);
}
BENCHMARK(BM_swapShorts_unaligned_2)->AT_COMMON_VALUES;

static void BM_swapInts_unaligned_2(benchmark::State& state) {
  swap_bench<jint, 2>(state, swapInts);
}
BENCHMARK(BM_swapInts_unaligned_2)->AT_COMMON_VALUES;

static void BM_swapLongs_unaligned_2(benchmark::State& state) {
  swap_bench<jlong, 2>(state, swapLongs);
}
BENCHMARK(BM_swapLongs_unaligned_2)->AT_COMMON_VALUES;


BENCHMARK_MAIN();
