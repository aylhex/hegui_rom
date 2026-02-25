#!/bin/bash

# Copyright 2014 The Android Open Source Project
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

readonly PREFIX="#####"
readonly RETRIES=2
test_prefix=

function checkArgOrExit() {
  if [[ $# -lt 2 ]]; then
    echo "Missing argument for option $1" >&2
    exit 1
  fi
}

function usageAndExit() {
  cat >&2 << EOF
  all_tests.sh - test runner with support for flake testing

  all_tests.sh [options]

  options:
  -h, --help                     show this menu
  -p, --prefix=TEST_PREFIX       specify a prefix for the tests to be run
EOF
  exit 0
}

function maybePlural() {
  # $1 = integer to use for plural check
  # $2 = singular string
  # $3 = plural string
  if [ $1 -ne 1 ]; then
    echo "$3"
  else
    echo "$2"
  fi
}

function runTest() {
  local cmd="$1"

  if $cmd; then
    return 0
  fi

  for iteration in $(seq $RETRIES); do
    if ! $cmd; then
      echo >&2 "'$cmd' failed more than once, giving up"
      return 1
    fi
  done

  echo >&2 "Warning: '$cmd' FLAKY, passed $RETRIES/$((RETRIES + 1))"
}

# Parse arguments
while [ -n "$1" ]; do
  case "$1" in
    -h|--help)
      usageAndExit
      ;;
    -p|--prefix)
      checkArgOrExit $@
      test_prefix=$2
      shift 2
      ;;
    *)
      echo "Unknown option $1" >&2
      echo >&2
      usageAndExit
      ;;
  esac
done

# Find the relevant tests
if [[ -z $test_prefix ]]; then
  readonly tests=$(eval "find . -name '*_test.py' -type f -executable")
else
  readonly tests=$(eval "find . -name '$test_prefix*' -type f -executable")
fi

# Give some readable status messages
readonly count=$(echo $tests | wc -w)
if [[ -z $test_prefix ]]; then
  echo "$PREFIX Found $count $(maybePlural $count test tests)."
else
  echo "$PREFIX Found $count $(maybePlural $count test tests) with prefix $test_prefix."
fi

exit_code=0

i=0
for test in $tests; do
  i=$((i + 1))
  echo ""
  echo "$PREFIX $test ($i/$count)"
  echo ""
  runTest $test || exit_code=$(( exit_code + 1 ))
  echo ""
done

echo "$PREFIX $exit_code failed $(maybePlural $exit_code test tests)."
exit $exit_code
