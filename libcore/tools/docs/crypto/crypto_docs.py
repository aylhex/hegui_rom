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

'''Utility functions for crypto doc updating tools.'''

import json


def load_json(filename):
    '''Returns an object containing the JSON data from the provided file.'''
    f = open(filename)
    # JSON doesn't allow comments, but we have some header docs in our file,
    # so strip comments out before parsing
    stripped_contents = ''
    for line in f:
        if not line.strip().startswith('#'):
            stripped_contents += line
    data = json.loads(stripped_contents)
    f.close()
    return data


def find_by_name(seq, name):
    """Returns the first element in seq with the given name."""
    for item in seq:
        if item['name'] == name:
            return item
    return None
