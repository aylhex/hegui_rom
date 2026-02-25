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

# Wrapper around checkpatch.sh to gather necessary information from the
# dist dir. Notably, this includes the git_sha1 and whether to suppress
# the check for post-submit.

set -e

export STATIC_ANALYSIS_SRC_DIR=$(dirname $(readlink -f $0))

source ${STATIC_ANALYSIS_SRC_DIR}/../envsetup.sh
export OUT_DIR=$(readlink -m ${OUT_DIR:-${ROOT_DIR}/out/${BRANCH}})
export DIST_DIR=$(readlink -m ${DIST_DIR:-${OUT_DIR}/dist})

APPLIED_PROP_PATH=${DIST_DIR}/applied.prop
BUILD_INFO_PATH=${DIST_DIR}/BUILD_INFO

verify_file_exists() {
  if [[ ! -f $1 ]]; then
    echo "Missing $1"
    exit 1
  fi
}

# Parse flags.
BUILD_ID=""
FORWARDED_ARGS=()
while [[ $# -gt 0 ]]; do
  next="$1"
  case ${next} in
  --bid)
    BUILD_ID="$2"
    shift
    ;;
  --help)
    echo "Checks whether given build is for presubmit. If so, extract git_sha1"
    echo "from repo.prop and invoke checkpatch.sh."
    echo ""
    echo "Usage: $0"
    echo "  <--bid nnn> (The build ID. Required.)"
    echo "  <args for checkpatch.sh>"
    exit 0
    ;;
  *)
    FORWARDED_ARGS+=("$1")
    ;;
  esac
  shift
done

if [[ -z $BUILD_ID ]]; then
  echo "WARNING: No --bid supplied. Assuming not presubmit build. Exiting."
  exit 0
fi

# Skip checkpatch for postsubmit (b/35390488).
set +e
echo "${BUILD_ID}" | grep -E "^P[0-9]+"
if [[ $? -ne 0 ]]; then
   echo "Did not identify a presubmit build. Exiting."
   exit 0
fi
set -e

# Pick the correct patch to test.
verify_file_exists ${APPLIED_PROP_PATH}
GIT_SHA1=$(grep -E "${KERNEL_DIR} [0-9a-f]+" "${APPLIED_PROP_PATH}" | awk '{print $2}')
if [[ -z ${GIT_SHA1} ]]; then
  # Since applied.prop only tracks user changes, ignore projects that are
  # included in presubmit without any changed files.
  echo "No changes to apply for ${KERNEL_DIR}."
  exit 0
fi

${STATIC_ANALYSIS_SRC_DIR}/checkpatch.sh --git_sha1 ${GIT_SHA1} ${FORWARDED_ARGS[*]}

