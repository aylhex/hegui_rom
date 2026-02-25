# source this file. Don't run it.

# Copyright (C) 2019 The Android Open Source Project
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Usage:
#   source build/envsetup.sh
#     to setup your path and cross compiler so that a kernel build command is
#     just:
#       make -j24

[ -n "$ENVSETUP_SH_INCLUDED" ] && return || export ENVSETUP_SH_INCLUDED=1

# TODO: Use a $(gettop) style method.
export ROOT_DIR=$PWD

export BUILD_CONFIG=${BUILD_CONFIG:-build.config}
. ${ROOT_DIR}/${BUILD_CONFIG}

export COMMON_OUT_DIR=$(readlink -m ${OUT_DIR:-${ROOT_DIR}/out/${BRANCH}})
export OUT_DIR=$(readlink -m ${COMMON_OUT_DIR}/${KERNEL_DIR})
export DIST_DIR=$(readlink -m ${DIST_DIR:-${COMMON_OUT_DIR}/dist})

echo "========================================================"
echo "= build config: ${ROOT_DIR}/${BUILD_CONFIG}"
cat ${ROOT_DIR}/${BUILD_CONFIG}

# List of prebuilt directories shell variables to incorporate into PATH
PREBUILTS_PATHS="
LINUX_GCC_CROSS_COMPILE_PREBUILTS_BIN
LINUX_GCC_CROSS_COMPILE_ARM32_PREBUILTS_BIN
CLANG_PREBUILT_BIN
LZ4_PREBUILTS_BIN
DTC_PREBUILTS_BIN
LIBUFDT_PREBUILTS_BIN
"

for PREBUILT_BIN in ${PREBUILTS_PATHS}; do
    PREBUILT_BIN=\${${PREBUILT_BIN}}
    eval PREBUILT_BIN="${PREBUILT_BIN}"
    if [ -n "${PREBUILT_BIN}" ]; then
        # Mitigate dup paths
        PATH=${PATH//"${ROOT_DIR}/${PREBUILT_BIN}:"}
        PATH=${ROOT_DIR}/${PREBUILT_BIN}:${PATH}
    fi
done
export PATH

echo
echo "PATH=${PATH}"
echo

export $(sed -n -e 's/\([^=]\)=.*/\1/p' ${ROOT_DIR}/${BUILD_CONFIG})

# verifies that defconfig matches the DEFCONFIG
function check_defconfig() {
    (cd ${OUT_DIR} && \
     make O=${OUT_DIR} savedefconfig)
    [ "$ARCH" = "x86_64" -o "$ARCH" = "i386" ] && local ARCH=x86
    echo Verifying that savedefconfig matches ${KERNEL_DIR}/arch/${ARCH}/configs/${DEFCONFIG}
    RES=0
    diff ${OUT_DIR}/defconfig ${KERNEL_DIR}/arch/${ARCH}/configs/${DEFCONFIG} ||
      RES=$?
    if [ ${RES} -ne 0 ]; then
        echo ERROR: savedefconfig does not match ${KERNEL_DIR}/arch/${ARCH}/configs/${DEFCONFIG}
    fi
    return ${RES}
}
