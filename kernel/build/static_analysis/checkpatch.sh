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

# Wrapper around checkpatch.pl to filter results.

set -e

export STATIC_ANALYSIS_SRC_DIR=$(dirname $(readlink -f $0))

ROOT_DIR="${STATIC_ANALYSIS_SRC_DIR}/../../"
pushd ${ROOT_DIR}
source ${STATIC_ANALYSIS_SRC_DIR}/../envsetup.sh
export OUT_DIR=$(readlink -m ${OUT_DIR:-${ROOT_DIR}/out/${BRANCH}})
export DIST_DIR=$(readlink -m ${DIST_DIR:-${OUT_DIR}/dist})
mkdir -p ${DIST_DIR}

export KERNEL_DIR=$(readlink -m ${KERNEL_DIR})

CHECKPATCH_PL_PATH="${KERNEL_DIR}/scripts/checkpatch.pl"
GIT_SHA1="HEAD"
PATCH_DIR="${OUT_DIR}/checkpatch/patches"
BLACKLIST_FILE="${STATIC_ANALYSIS_SRC_DIR}/checkpatch_blacklist"
RESULTS_PATH=${DIST_DIR}/checkpatch.log
RETURN_CODE=0

echoerr() {
  echo "$@" 1>&2;
}

# Parse flags.
CHECKPATCH_ARGS=(--show-types)
while [[ $# -gt 0 ]]; do
  next="$1"
  case ${next} in
  --git_sha1)
    GIT_SHA1="$2"
    shift
    ;;
  --blacklisted_checks)
    BLACKLIST_FILE="$2"
    shift
    ;;
  --help)
    echo "Gets a patch from git, passes it checkpatch.pl, and then reports"
    echo "the subset of violations we choose to enforce."
    echo ""
    echo "Usage: $0"
    echo "  <--git_sha1 nnn> (Defaults to HEAD)"
    echo "  <--blacklisted_checks path_to_file> (Defaults to checkpatch_blacklist)"
    echo "  <args for checkpatch.pl>"
    exit 0
    ;;
  *)
    CHECKPATCH_ARGS+=("$1")
    ;;
  esac
  shift
done


# Clean up from any previous run.
if [[ -d "${PATCH_DIR}" ]]; then
  rm -fr "${PATCH_DIR}"
fi
mkdir -p "${PATCH_DIR}"

# Update blacklist.
if [[ -f "${BLACKLIST_FILE}" ]]; then
  IGNORED_ERRORS=$(grep -v '^#' ${BLACKLIST_FILE} | paste -s -d,)
  if [[ -n "${IGNORED_ERRORS}" ]]; then
    CHECKPATCH_ARGS+=(--ignore)
    CHECKPATCH_ARGS+=("${IGNORED_ERRORS}")
  fi
fi

echo "========================================================"
echo " Running static analysis..."
echo "========================================================"
echo "Using KERNEL_DIR: ${KERNEL_DIR}"
echo "Using --git_sha1: ${GIT_SHA1}"

# Generate patch file from git.
cd ${KERNEL_DIR}
git format-patch --quiet -o "${PATCH_DIR}" "${GIT_SHA1}^1..${GIT_SHA1}"
PATCH_FILE="${PATCH_DIR}/*.patch"

# Delay exit on non-zero checkpatch.pl return code so we can finish logging.

# Note, it's tricky to ignore this exit code completely and instead return only
# based on the log values. For example, if the log is not empty, but contains no
# ERRORS, how do we reliabliy distinguish WARNINGS that were not blacklisted
# (or other conditions we want to ignore), from legitimate errors running the
# script itself (e.g. bad flags)? checkpatch.pl will return 1 in both cases.
# For now, include all known warnings in the blacklist, and forward this code
# unconditionally.

set +e
"${CHECKPATCH_PL_PATH}" ${CHECKPATCH_ARGS[*]} $PATCH_FILE > "${RESULTS_PATH}"
CHECKPATCH_RC=$?
set -e

# Summarize errors in the build log (full copy included in dist dir).
if [[ $CHECKPATCH_RC -ne 0 ]]; then
  echoerr "Errors were reported from checkpatch.pl."
  echoerr ""
  echoerr "Summary:"
  echoerr ""
  { grep -r -h -E -A1 "^ERROR:" "${RESULTS_PATH}" 1>&2; } || true
  echoerr ""
  echoerr "See $(basename ${RESULTS_PATH}) for complete output."
fi

echo "========================================================"
echo "Finished running static analysis."
echo "========================================================"
popd
exit ${CHECKPATCH_RC}
