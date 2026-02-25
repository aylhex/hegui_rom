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
#include <linux/filter.h>
#include <linux/seccomp.h>
#include <sys/stat.h>
#include <sys/prctl.h>
#include <string>
#include <sys/syscall.h>
#include <errno.h>

#include <jni.h>
#include <nativehelper/JNIHelp.h>
#include <nativehelper/ScopedUtfChars.h>

extern "C" void Java_libcore_java_io_FileTest_nativeTestFilesWithSurrogatePairs(
    JNIEnv* env, jobject /* clazz */, jstring baseDir) {
  ScopedUtfChars baseDirUtf(env, baseDir);

  std::string base(baseDirUtf.c_str());
  std::string subDir = base + "/dir_\xF0\x93\x80\x80";
  std::string subFile = subDir + "/file_\xF0\x93\x80\x80";

  struct stat sb;
  int ret = stat(subDir.c_str(), &sb);
  if (ret == -1) {
      jniThrowIOException(env, errno);
  }
  if (!S_ISDIR(sb.st_mode)) {
      jniThrowException(env, "java/lang/IllegalStateException", "expected dir");
  }

  ret = stat(subFile.c_str(), &sb);
  if (ret == -1) {
      jniThrowIOException(env, errno);
  }

  if (!S_ISREG(sb.st_mode)) {
      jniThrowException(env, "java/lang/IllegalStateException", "expected file");
  }
}

extern "C" int Java_libcore_java_io_FileTest_installSeccompFilter(JNIEnv* , jclass /* clazz */) {
    struct sock_filter filter[] = {
        BPF_STMT(BPF_LD|BPF_W|BPF_ABS, offsetof(struct seccomp_data, nr)),

// for arm, mips, x86.
#ifdef __NR_fstatat64
        BPF_JUMP(BPF_JMP|BPF_JEQ|BPF_K, __NR_fstatat64, 0, 1),
#else
// for arm64, x86_64.
        BPF_JUMP(BPF_JMP|BPF_JEQ|BPF_K, __NR_newfstatat, 0, 1),
#endif
        BPF_STMT(BPF_RET|BPF_K, SECCOMP_RET_ERRNO | EPERM),
        BPF_STMT(BPF_RET|BPF_K, SECCOMP_RET_ALLOW),
    };
    struct sock_fprog prog = {
        .len = (unsigned short)(sizeof(filter)/sizeof(filter[0])),
        .filter = filter,
    };
    long ret = prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0);

    return ret = prctl(PR_SET_SECCOMP, SECCOMP_MODE_FILTER, &prog);
}
