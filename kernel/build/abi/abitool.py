#!/usr/bin/env python3
#
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
#

import subprocess
import logging

log = logging.getLogger(__name__)

class AbiTool(object):
    """ Base class for different kinds of abi analysis tools"""
    def dump_kernel_abi(self, linux_tree, dump_path):
        raise NotImplementedError()

    def diff_abi(self, old_dump, new_dump, diff_report):
        raise NotImplementedError()

    def name(self):
        raise NotImplementedError()

class Libabigail(AbiTool):
    """" Concrete AbiTool implementation for libabigail """
    def dump_kernel_abi(self, linux_tree, dump_path):
        dump_abi_cmd = ['abidw',
                        '--linux-tree',
                        linux_tree,
                        '--out-file',
                        dump_path]
        subprocess.check_call(dump_abi_cmd)

    def diff_abi(self, old_dump, new_dump, diff_report):
        log.info('libabigail diffing: {} and {} at {}'.format(old_dump,
                                                                new_dump,
                                                                diff_report))
        diff_abi_cmd = ['abidiff',
                        '--impacted-interfaces',
                        '--leaf-changes-only',
                        '--dump-diff-tree',
                        old_dump,
                        new_dump]

        with open(diff_report, 'w') as out:
            try:
                subprocess.check_call(diff_abi_cmd, stdout=out, stderr=out)
            except subprocess.CalledProcessError as e:
                if e.returncode in (1, 2):  # abigail error, user error
                    raise
                return True  # actual abi change

        return False  # no abi change

def get_abi_tool(abi_tool):
    if abi_tool == 'libabigail':
        log.info('using libabigail for abi analysis')
        return Libabigail()

    raise ValueError("not a valid abi_tool: %s" % abi_tool)

