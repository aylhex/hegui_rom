#!/usr/bin/env python
#
# Copyright (C) 2017 The Android Open Source Project
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Updates a JSON data file of supported algorithms.

Takes input on stdin a list of provided algorithms as produced by
ListProviders.java along with a JSON file of the previous set of algorithm
support and what the current API level is, and produces an updated JSON
record of algorithm support.
"""

import argparse
import collections
import datetime
import json
import re
import sys

import crypto_docs

SUPPORTED_CATEGORIES = [
    'AlgorithmParameterGenerator',
    'AlgorithmParameters',
    'CertificateFactory',
    'CertPathBuilder',
    'CertPathValidator',
    'CertStore',
    'Cipher',
    'KeyAgreement',
    'KeyFactory',
    'KeyGenerator',
    'KeyManagerFactory',
    'KeyPairGenerator',
    'KeyStore',
    'Mac',
    'MessageDigest',
    'SecretKeyFactory',
    'SecureRandom',
    'Signature',
    'SSLContext',
    'SSLEngine.Enabled',
    'SSLEngine.Supported',
    'SSLSocket.Enabled',
    'SSLSocket.Supported',
    'TrustManagerFactory',
]

# For these categories, we really want to maintain the casing that was in the
# original data, so avoid changing it.
CASE_SENSITIVE_CATEGORIES = [
    'SSLEngine.Enabled',
    'SSLEngine.Supported',
    'SSLSocket.Enabled',
    'SSLSocket.Supported',
]


find_by_name = crypto_docs.find_by_name


def find_by_normalized_name(seq, name):
    """Returns the first element in seq with the given normalized name."""
    for item in seq:
        if normalize_name(item['name']) == name:
            return item
    return None


def sort_by_name(seq):
    """Returns a copy of the input sequence sorted by name."""
    return sorted(seq, key=lambda x: x['name'])


def normalize_name(name):
    """Returns a normalized version of the given algorithm name."""
    name = name.upper()
    # BouncyCastle uses X.509 with an alias of X509, Conscrypt does the
    # reverse.  X.509 is the official name of the standard, so use that.
    if name == "X509":
        name = "X.509"
    # PKCS5PADDING and PKCS7PADDING are the same thing (more accurately, PKCS#5
    # is a special case of PKCS#7), but providers are inconsistent in their
    # naming.  Use PKCS5PADDING because that's what our docs have used
    # historically.
    if name.endswith("/PKCS7PADDING"):
        name = name[:-1 * len("/PKCS7PADDING")] + "/PKCS5PADDING"
    return name


def fix_name_caps_for_output(name):
    """Returns a version of the given algorithm name with capitalization fixed."""
    # It's important that this must only change the capitalization of the
    # name, not any of its text, otherwise future runs won't be able to
    # match this name with the name coming from the device.

    # We current make the following capitalization fixes
    # DESede (not DESEDE)
    # FOOwithBAR (not FOOWITHBAR or FOOWithBAR)
    # Hmac (not HMAC)
    name = re.sub('WITH', 'with', name, flags=re.I)
    name = re.sub('DESEDE', 'DESede', name, flags=re.I)
    name = re.sub('HMAC', 'Hmac', name, flags=re.I)
    return name


def get_current_data(f):
    """Returns a map of the algorithms in the given input.

    The input file-like object must supply a "BEGIN ALGORITHM LIST" line
    followed by any number of lines of an algorithm category and algorithm name
    separated by whitespace followed by a "END ALGORITHM LIST" line.  The
    input can supply arbitrary values outside of the BEGIN and END lines, it
    will be ignored.

    The returned algorithms will have their names normalized.

    Returns:
      A dict of categories to lists of normalized algorithm names and a
        dict of normalized algorithm names to original algorithm names.

    Raises:
      EOFError: If either the BEGIN or END sentinel lines are not present.
      ValueError: If a line between the BEGIN and END sentinel lines is not
        made up of two identifiers separated by whitespace.
    """
    current_data = collections.defaultdict(list)
    name_dict = {}

    saw_begin = False
    saw_end = False
    for line in f.readlines():
        line = line.strip()
        if not saw_begin:
            if line.strip() == 'BEGIN ALGORITHM LIST':
                saw_begin = True
            continue
        if line == 'END ALGORITHM LIST':
            saw_end = True
            break
        category, algorithm = line.split()
        if category not in SUPPORTED_CATEGORIES:
            continue
        normalized_name = normalize_name(algorithm)
        current_data[category].append(normalized_name)
        name_dict[normalized_name] = algorithm

    if not saw_begin:
        raise EOFError(
            'Reached the end of input without encountering the begin sentinel')
    if not saw_end:
        raise EOFError(
            'Reached the end of input without encountering the end sentinel')
    return dict(current_data), name_dict


def update_data(prev_data, current_data, name_dict, api_level, date):
    """Returns a copy of prev_data, modified to take into account current_data.

    Updates the algorithm support metadata structure by starting with the
    information in prev_data and updating it to take into account the algorithms
    listed in current_data.  Algorithms not present in current_data will still
    be present in the return value, but their supported_api_levels may be
    modified to indicate that they are no longer supported.

    Args:
      prev_data: The data on algorithm support from the previous API level.
      current_data: The algorithms supported in the current API level, as a map
        from algorithm category to list of algorithm names.
      api_level: An integer representing the current API level.
      date: A datetime object containing the time of update.
    """
    new_data = {'categories': []}

    for category in SUPPORTED_CATEGORIES:
        prev_category = find_by_name(prev_data['categories'], category)
        if prev_category is None:
            prev_category = {'name': category, 'algorithms': []}
        current_category = (
            current_data[category] if category in current_data else [])
        new_category = {'name': category, 'algorithms': []}
        prev_algorithms = [normalize_name(x['name']) for x in prev_category['algorithms']]
        alg_union = set(prev_algorithms) | set(current_category)
        for alg in alg_union:
            prev_alg = find_by_normalized_name(prev_category['algorithms'], alg)
            if prev_alg is not None:
                new_algorithm = {'name': prev_alg['name']}
            elif alg in name_dict:
                new_algorithm = {'name': name_dict[alg]}
            else:
                new_algorithm = {'name': alg}
            if category not in CASE_SENSITIVE_CATEGORIES:
                new_algorithm['name'] = fix_name_caps_for_output(new_algorithm['name'])
            new_level = None
            if alg in current_category and alg in prev_algorithms:
                # Both old and new have it, just ensure the API level is right
                if prev_alg['supported_api_levels'].endswith('+'):
                    new_level = prev_alg['supported_api_levels']
                else:
                    new_level = (prev_alg['supported_api_levels']
                                 + ',%d+' % api_level)
            elif alg in prev_algorithms:
                # Only in the old set, so ensure the API level is marked
                # as ending
                if prev_alg['supported_api_levels'].endswith('+'):
                    # The algorithm is newly missing, so modify the support
                    # to end at the previous level
                    new_level = prev_alg['supported_api_levels'][:-1]
                    if not new_level.endswith(str(api_level - 1)):
                        new_level += '-%d' % (api_level - 1)
                else:
                    new_level = prev_alg['supported_api_levels']
                new_algorithm['deprecated'] = 'true'
            else:
                # Only in the new set, so add it
                new_level = '%d+' % api_level
            if alg in prev_algorithms and 'note' in prev_alg:
                new_algorithm['note'] = prev_alg['note']
            new_algorithm['supported_api_levels'] = new_level
            new_category['algorithms'].append(new_algorithm)
        if new_category['algorithms']:
            new_category['algorithms'] = sort_by_name(
                new_category['algorithms'])
            new_data['categories'].append(new_category)
    new_data['categories'] = sort_by_name(new_data['categories'])
    new_data['api_level'] = str(api_level)
    new_data['last_updated'] = date.strftime('%Y-%m-%d %H:%M:%S UTC')

    return new_data


def main():
    parser = argparse.ArgumentParser(description='Update JSON support file')
    parser.add_argument('--api_level',
                        required=True,
                        type=int,
                        help='The current API level')
    parser.add_argument('--rewrite_file',
                        action='store_true',
                        help='If specified, rewrite the'
                             ' input file with the result')
    parser.add_argument('file',
                        help='The JSON file to update')
    args = parser.parse_args()

    prev_data = crypto_docs.load_json(args.file)

    current_data, name_dict = get_current_data(sys.stdin)

    new_data = update_data(prev_data,
                           current_data,
                           name_dict,
                           args.api_level,
                           datetime.datetime.utcnow())

    if args.rewrite_file:
        f = open(args.file, 'w')
        f.write('# This file is autogenerated.'
                '  See libcore/tools/docs/crypto/README for details.\n')
        json.dump(
            new_data, f, indent=2, sort_keys=True, separators=(',', ': '))
        f.close()
    else:
        print json.dumps(
            new_data, indent=2, sort_keys=True, separators=(',', ': '))


if __name__ == '__main__':
    main()
