#!/usr/bin/env bash
#
# Updates the crypto support JSON data file by running the appropriate tools.

# Ensure that the files we need are in the place we expect
if [ ! -f libcore/tools/docs/crypto/src/java/libcore/java/security/ListProviders.java -o ! -f libcore/tools/docs/crypto/data/crypto_support.json ]; then
  echo "This command must be run from the repo root."
  exit 1
fi

if [ -z "$1" ]; then
  echo "The current API level must be specified as an argument."
  exit 1
fi

make -j48 vogar dx
vogar --mode=activity --multidex=false libcore/tools/docs/crypto/src/java/libcore/java/security/ListProviders.java | libcore/tools/docs/crypto/update_crypto_support.py --api_level=$1 --rewrite_file libcore/tools/docs/crypto/data/crypto_support.json
