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

import datetime
import StringIO
import unittest
import update_crypto_support


def do_update_data(prev_data, current_data, name_dict={}):
    return update_crypto_support.update_data(
        prev_data,
        current_data,
        name_dict,
        72,
        datetime.datetime.utcfromtimestamp(1234567890))


# The timestamp 1234567890 in our text format
LAST_UPDATED_TEXT = '2009-02-13 23:31:30 UTC'


class TestUpdateData(unittest.TestCase):
    maxDiff = None
    def test_find_by_name(self):
        self.assertIsNone(update_crypto_support.find_by_name([], 'foo'))
        self.assertIsNone(
            update_crypto_support.find_by_name([{'name': 'foo'}], 'bar'))
        self.assertEqual(
            update_crypto_support.find_by_name(
                [{'name': 'foo', 'value': 'foo_value'}],
                'foo'),
            {'name': 'foo', 'value': 'foo_value'})
        self.assertEqual(
            update_crypto_support.find_by_name(
                [{'name': 'foo', 'value': 'foo_value'},
                 {'name': 'bar', 'value': 'bar_value'}],
                'bar'),
            {'name': 'bar', 'value': 'bar_value'})
        self.assertEqual(
            update_crypto_support.find_by_name(
                [{'name': 'foo', 'value': 'foo_value'},
                 {'name': 'bar', 'value': 'bar_value'},
                 {'name': 'foo', 'value': 'foo2_value'}],
                'foo'),
            {'name': 'foo', 'value': 'foo_value'})
        self.assertEqual(
            update_crypto_support.find_by_name(
                [{'name': 'foot', 'value': 'foot_value'},
                 {'name': 'bar', 'value': 'bar_value'},
                 {'name': 'foo', 'value': 'foo_value'}],
                'foo'),
            {'name': 'foo', 'value': 'foo_value'})

    def test_sort_by_name(self):
        self.assertEqual(update_crypto_support.sort_by_name([]), [])
        self.assertEqual(
            update_crypto_support.sort_by_name(
                [{'name': 'foot', 'value': 'foot_value'},
                 {'name': 'bar', 'value': 'bar_value'},
                 {'name': 'foo', 'value': 'foo_value'}]),
            [{'name': 'bar', 'value': 'bar_value'},
             {'name': 'foo', 'value': 'foo_value'},
             {'name': 'foot', 'value': 'foot_value'}])
        with self.assertRaises(KeyError):
            update_crypto_support.sort_by_name([{'not_name': 'foo'}])

    def test_get_current_data(self):
        self.assertEqual(update_crypto_support.get_current_data(
            StringIO.StringIO(
                '''
                BEGIN ALGORITHM LIST
                Mac Bob
                Mac Jones
                MessageDigest Jim
                Mac Amy
                OtherThing Mary
                END ALGORITHM LIST
                ''')),
            ({'Mac': ['BOB', 'JONES', 'AMY'],
              'MessageDigest': ['JIM']},
             {'AMY': 'Amy',
              'BOB': 'Bob',
              'JONES': 'Jones',
              'JIM': 'Jim'}))
        self.assertEqual(update_crypto_support.get_current_data(
            StringIO.StringIO(
                '''
                BEGIN ALGORITHM LIST
                Mac Dupe
                Mac Jones
                MessageDigest Jim
                Mac Amy
                Mac Dupe
                OtherThing Mary
                END ALGORITHM LIST
                ''')),
            ({'Mac': ['DUPE', 'JONES', 'AMY', 'DUPE'],
              'MessageDigest': ['JIM']},
             {'AMY': 'Amy',
              'DUPE': 'Dupe',
              'JONES': 'Jones',
              'JIM': 'Jim'}))
        self.assertEqual(update_crypto_support.get_current_data(
            StringIO.StringIO(
                '''
                Mac NotAValue
                BEGIN ALGORITHM LIST
                Mac Bob
                Mac Jones
                MessageDigest Jim
                Mac Amy
                OtherThing Mary
                END ALGORITHM LIST
                Mac AlsoNotAValue
                ''')),
            ({'Mac': ['BOB', 'JONES', 'AMY'],
              'MessageDigest': ['JIM']},
             {'AMY': 'Amy',
              'BOB': 'Bob',
              'JONES': 'Jones',
              'JIM': 'Jim'}))
        self.assertEqual(update_crypto_support.get_current_data(
            StringIO.StringIO(
                '''
                BEGIN ALGORITHM LIST OF LISTS
                Mac NotAValue
                BEGIN ALGORITHM LIST
                Mac Bob
                Mac Jones
                MessageDigest Jim
                Mac Amy
                OtherThing Mary
                END ALGORITHM LIST
                ''')),
            ({'Mac': ['BOB', 'JONES', 'AMY'],
              'MessageDigest': ['JIM']},
             {'AMY': 'Amy',
              'BOB': 'Bob',
              'JONES': 'Jones',
              'JIM': 'Jim'}))
        with self.assertRaises(EOFError):
            update_crypto_support.get_current_data(StringIO.StringIO(
                '''
                NOTBEGIN ALGORITHM LIST
                Mac Bob
                Mac Jones
                MessageDigest Jim
                Mac Amy
                OtherThing Mary
                END ALGORITHM LIST
                '''))
        with self.assertRaises(EOFError):
            update_crypto_support.get_current_data(StringIO.StringIO(
                '''
                BEGIN ALGORITHM LIST
                Mac Bob
                Mac Jones
                MessageDigest Jim
                Mac Amy
                OtherThing Mary'''))
        with self.assertRaises(ValueError):
            update_crypto_support.get_current_data(StringIO.StringIO(
                '''
                BEGIN ALGORITHM LIST
                Mac Bob
                Mac Jones
                MessageDigest Jim OneTooManyItems
                Mac Amy
                OtherThing Mary
                END ALGORITHM LIST
                '''))
        with self.assertRaises(ValueError):
            update_crypto_support.get_current_data(StringIO.StringIO(
                '''
                BEGIN ALGORITHM LIST
                Mac Bob
                Mac Jones
                TooFewItems
                MessageDigest Jim
                Mac Amy
                OtherThing Mary
                END ALGORITHM LIST
                '''))

    def test_update_data_no_data(self):
        self.assertEqual(
            do_update_data(
                {'categories': []},
                {}),
            {'categories': [],
             'api_level': '72',
             'last_updated': LAST_UPDATED_TEXT})

        self.assertEqual(
            do_update_data(
                {'categories': [
                    {'name': 'MessageDigest',
                     'algorithms': []}]},
                {}),
            {'categories': [],
             'api_level': '72',
             'last_updated': LAST_UPDATED_TEXT})

        self.assertEqual(
            do_update_data(
                {'categories': []},
                {'MessageDigest': []}),
            {'categories': [],
             'api_level': '72',
             'last_updated': LAST_UPDATED_TEXT})

    def test_update_data_no_updates(self):
        self.assertEqual(
            do_update_data(
                {'categories': [
                    {'name': 'MessageDigest',
                     'algorithms': [
                         {'name': 'SHA-1',
                          'supported_api_levels': '1+'},
                         {'name': 'SHA-2',
                          'supported_api_levels': '1-22',
                          'deprecated': 'true'}]}]},
                {'MessageDigest': ['SHA-1']}),
            {'categories': [
                {'name': 'MessageDigest',
                 'algorithms': [
                     {'name': 'SHA-1',
                      'supported_api_levels': '1+'},
                     {'name': 'SHA-2',
                      'supported_api_levels': '1-22',
                      'deprecated': 'true'}]}],
                'api_level': '72',
                'last_updated': LAST_UPDATED_TEXT})

    def test_update_data_new_item(self):
        self.assertEqual(
            do_update_data(
                {'categories': [
                    {'name': 'MessageDigest',
                     'algorithms': [
                         {'name': 'SHA-1',
                          'supported_api_levels': '1+'},
                         {'name': 'SHA-2',
                          'supported_api_levels': '1-22',
                          'deprecated': 'true'},
                         {'name': 'SHA-384',
                          'supported_api_levels': '17-32'}]}]},
                {'MessageDigest': ['SHA-1', 'SHA-256', 'SHA-384']}),
            {'categories': [
                {'name': 'MessageDigest',
                 'algorithms': [
                     {'name': 'SHA-1',
                      'supported_api_levels': '1+'},
                     {'name': 'SHA-2',
                      'supported_api_levels': '1-22',
                      'deprecated': 'true'},
                     {'name': 'SHA-256',
                      'supported_api_levels': '72+'},
                     {'name': 'SHA-384',
                      'supported_api_levels': '17-32,72+'}]}],
                'api_level': '72',
                'last_updated': LAST_UPDATED_TEXT})

    def test_update_data_removed_item(self):
        self.assertEqual(
            do_update_data(
                {'categories': [
                    {'name': 'MessageDigest',
                     'algorithms': [
                         {'name': 'SHA-1',
                          'supported_api_levels': '1+'},
                         {'name': 'SHA-2',
                          'supported_api_levels': '1-22',
                          'deprecated': 'true'},
                         {'name': 'SHA-256',
                          'supported_api_levels': '70+'},
                         {'name': 'SHA-384',
                          'supported_api_levels': '71+'},
                         {'name': 'SHA-512',
                          'supported_api_levels': '1-3,17-32,47+'}]}]},
                {'MessageDigest': ['SHA-1']}),
            {'categories': [
                {'name': 'MessageDigest',
                 'algorithms': [
                     {'name': 'SHA-1',
                      'supported_api_levels': '1+'},
                     {'name': 'SHA-2',
                      'supported_api_levels': '1-22',
                      'deprecated': 'true'},
                     {'name': 'SHA-256',
                      'supported_api_levels': '70-71',
                      'deprecated': 'true'},
                     {'name': 'SHA-384',
                      'supported_api_levels': '71',
                      'deprecated': 'true'},
                     {'name': 'SHA-512',
                      'supported_api_levels': '1-3,17-32,47-71',
                      'deprecated': 'true'}]}],
                'api_level': '72',
                'last_updated': LAST_UPDATED_TEXT})

    def test_update_data_duplicates(self):
        self.assertEqual(
            do_update_data(
                {'categories': [
                    {'name': 'MessageDigest',
                     'algorithms': [
                         {'name': 'SHA-1',
                          'supported_api_levels': '1+'},
                         {'name': 'SHA-2',
                          'supported_api_levels': '1-22',
                          'deprecated': 'true'},
                         {'name': 'SHA-1',
                          'supported_api_levels': '7+'}]}]},
                {'MessageDigest': ['SHA-1']}),
            {'categories': [
                {'name': 'MessageDigest',
                 'algorithms': [
                     {'name': 'SHA-1',
                      'supported_api_levels': '1+'},
                     {'name': 'SHA-2',
                      'supported_api_levels': '1-22',
                      'deprecated': 'true'}]}],
                'api_level': '72',
                'last_updated': LAST_UPDATED_TEXT})

        self.assertEqual(
            do_update_data(
                {'categories': [
                    {'name': 'MessageDigest',
                     'algorithms': [
                         {'name': 'SHA-1',
                          'supported_api_levels': '1+'},
                         {'name': 'SHA-2',
                          'supported_api_levels': '1-22',
                          'deprecated': 'true'}]}]},
                {'MessageDigest': ['SHA-1', 'SHA-1']}),
            {'categories': [
                {'name': 'MessageDigest',
                 'algorithms': [
                     {'name': 'SHA-1',
                      'supported_api_levels': '1+'},
                     {'name': 'SHA-2',
                      'supported_api_levels': '1-22',
                      'deprecated': 'true'}]}],
                'api_level': '72',
                'last_updated': LAST_UPDATED_TEXT})

    def test_update_data_preserve_notes(self):
        self.assertEqual(
            do_update_data(
                {'categories': [
                    {'name': 'MessageDigest',
                     'algorithms': [
                         {'name': 'SHA-1',
                          'note': 'SHA-1 note',
                          'supported_api_levels': '1+'},
                         {'name': 'SHA-2',
                          'supported_api_levels': '1-22',
                          'deprecated': 'true'}]}]},
                {'MessageDigest': ['SHA-1']}),
            {'categories': [
                {'name': 'MessageDigest',
                 'algorithms': [
                     {'name': 'SHA-1',
                      'note': 'SHA-1 note',
                      'supported_api_levels': '1+'},
                     {'name': 'SHA-2',
                      'supported_api_levels': '1-22',
                      'deprecated': 'true'}]}],
                'api_level': '72',
                'last_updated': LAST_UPDATED_TEXT})

    def test_update_name_matching(self):
        self.assertEqual(
            do_update_data(
                {'categories': [
                    {'name': 'MessageDigest',
                     'algorithms': [
                         {'name': 'sha-1',
                          'supported_api_levels': '1+'},
                         {'name': 'Sha-2',
                          'supported_api_levels': '1-22',
                          'deprecated': 'true'},
                         {'name': 'SHA-3',
                          'supported_api_levels': '7+'}]}]},
                {'MessageDigest': ['SHA-1', 'SHA-2', 'SHA-3']},
                {'SHA-1': 'Sha-1', 'SHA-2': 'Sha-2', 'SHA-3': 'Sha-3'}),
            {'categories': [
                {'name': 'MessageDigest',
                 'algorithms': [
                     {'name': 'SHA-3',
                      'supported_api_levels': '7+'},
                     {'name': 'Sha-2',
                      'supported_api_levels': '1-22,72+'},
                     {'name': 'sha-1',
                      'supported_api_levels': '1+'}]}],
                'api_level': '72',
                'last_updated': LAST_UPDATED_TEXT})
        self.assertEqual(
            do_update_data(
                {'categories': [
                    {'name': 'MessageDigest',
                     'algorithms': [
                         {'name': 'Sha-2',
                          'supported_api_levels': '1-22',
                          'deprecated': 'true'},
                         {'name': 'SHA-3',
                          'supported_api_levels': '7+'},
                         {'name': 'sha-1',
                          'supported_api_levels': '1+'}]}]},
                {'MessageDigest': ['SHA-1', 'SHA-3']},
                {'SHA-1': 'Sha-1', 'SHA-3': 'Sha-3'}),
            {'categories': [
                {'name': 'MessageDigest',
                 'algorithms': [
                     {'name': 'SHA-3',
                      'supported_api_levels': '7+'},
                     {'name': 'Sha-2',
                      'supported_api_levels': '1-22',
                      'deprecated': 'true'},
                     {'name': 'sha-1',
                      'supported_api_levels': '1+'}]}],
                'api_level': '72',
                'last_updated': LAST_UPDATED_TEXT})


if __name__ == '__main__':
    unittest.main()
