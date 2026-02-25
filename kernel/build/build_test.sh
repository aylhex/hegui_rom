#!/bin/bash

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
#   build/build_test.sh

export MAKE_ARGS=$@
export ROOT_DIR=$(dirname $(readlink -f $0))
export NET_TEST=${ROOT_DIR}/../kernel/tests/net/test

# if device has its own build.config.net_test in the
# root (via manifest copy rule) then use it, otherwise
# use the default one in the build/ directory. if the
# BUILD_CONFIG is already specified in the environment,
# it overrides everything (unless it does not exist.)
if [ -z "$BUILD_CONFIG" ]; then
  BUILD_CONFIG=build.config.net_test
fi
if [ ! -e $BUILD_CONFIG ]; then
  BUILD_CONFIG=build/${BUILD_CONFIG}
fi
export BUILD_CONFIG

test=all_tests.sh
set -e
source ${ROOT_DIR}/envsetup.sh
export OUT_DIR=$(readlink -m ${OUT_DIR:-${ROOT_DIR}/out/${BRANCH}})
mkdir -p ${OUT_DIR}

# build.config.net_test sets KERNEL_DIR to "private/*", which doesn't work for
# common kernels, where the code is in "common/". Check for that here. We could
# also require that each of these kernels have their own build.config.net_test,
# but that complicates the manifests.
if ! [ -f $KERNEL_DIR/Makefile ] && [ -f common/Makefile ]; then
  KERNEL_DIR=common
fi
export KERNEL_DIR=$(readlink -m ${KERNEL_DIR})

echo "========================================================"
echo " Building kernel and running tests "
echo "    Using KERNEL_DIR: " ${KERNEL_DIR}
echo "    Using OUT_DIR   : " ${OUT_DIR}

cd ${OUT_DIR}
$NET_TEST/run_net_test.sh --builder $test
echo $?
echo "======Finished running tests======"
