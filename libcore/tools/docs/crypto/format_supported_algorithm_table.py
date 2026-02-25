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

"""Outputs HTML based on an input JSON file.

Outputs HTML tables suitable for inclusion in the Android documentation that
reflect the crypto algorithm support shown in the provided data file.
"""

import argparse
import operator

import crypto_docs


find_by_name = crypto_docs.find_by_name


def sort_by_name(seq):
    return sorted(seq, key=lambda x: x['name'])


def has_notes(category):
    for algorithm in category['algorithms']:
        if 'note' in algorithm:
            return True
    return False


# Prevents the given value from being word-wrapped.  This is mainly to ensure that
# long identifiers with hyphens, like OAEPwithSHA-1andMGF1Padding, don't get word-wrapped
# at the hyphen.
def nowrap(value):
    return '<span style="white-space: nowrap">%s</span>' % value


def main():
    parser = argparse.ArgumentParser(description='Output algorithm support HTML tables')
    parser.add_argument('--for_javadoc',
                        action='store_true',
                        help='If specified, format for inclusion in class documentation')
    parser.add_argument('--category',
                        action='append',
                        help='The category to display, may be specified multiple times')
    parser.add_argument('file',
                        help='The JSON file to use for data')
    args = parser.parse_args()

    output = []
    data = crypto_docs.load_json(args.file)
    categories = sort_by_name(data['categories'])
    output.append('<h2 id="SupportedAlgorithms">Supported Algorithms</h2>')
    output.append('')
    output.append('<ul>')
    for category in categories:
        if not category['name'].endswith('.Enabled'):
            output.append('  <li><a href="#Supported{name}">'
                   '<code>{name}</code></a></li>'.format(**category))
    output.append('</ul>')
    for category in categories:
        if args.category and category['name'] not in args.category:
            continue
        show_notes = has_notes(category)
        if category['name'].endswith('.Enabled'):
            # These are handled in the "Supported" section below
            continue
        if category['name'] == 'Cipher':
            # We display ciphers in a four-column table to conserve space and
            # so that it's more comprehensible.  To do this, we have to
            # collapse all our ciphers into "equivalence classes" of a sort.

            # First, collect the relevant data for each algorithm into a tuple.
            # The mode and padding are in lists because we are going to collapse
            # multiple tuples with those in later steps.
            algorithms = sort_by_name(category['algorithms'])
            tuples = []
            for algorithm in algorithms:
                name, mode, padding = algorithm['name'].split('/')
                tuples.append((
                    name,
                    [mode],
                    [padding],
                    algorithm['supported_api_levels'],
                    'deprecated' in algorithm and algorithm['deprecated'],
                    algorithm.get('note', '')))
            # Sort the tuples by all items except padding, then collapse
            # items with all non-padding values the same (which will always be
            # neighboring items) into a single item.
            tuples.sort(key=operator.itemgetter(0, 1, 3, 4))
            i = 0
            while i < len(tuples) - 1:
                if (tuples[i][0] == tuples[i+1][0]
                    and tuples[i][1] == tuples[i+1][1]
                    and tuples[i][3] == tuples[i+1][3]
                    and tuples[i][4] == tuples[i+1][4]
                    and tuples[i][5] == tuples[i+1][5]):
                    tuples[i][2].extend(tuples[i+1][2])
                    del tuples[i+1]
                else:
                    i += 1
            # Do the same thing as above, but with modes.
            tuples.sort(key=operator.itemgetter(0, 2, 3, 4))
            i = 0
            while i < len(tuples) - 1:
                if (tuples[i][0] == tuples[i+1][0]
                    and tuples[i][2] == tuples[i+1][2]
                    and tuples[i][3] == tuples[i+1][3]
                    and tuples[i][4] == tuples[i+1][4]
                    and tuples[i][5] == tuples[i+1][5]):
                    tuples[i][1].extend(tuples[i+1][1])
                    del tuples[i+1]
                else:
                    i += 1
            # Display the table with rowspans for those entries where all the
            # items have the same algorithm, mode, etc
            output.append('<h3 id="Supported{name}">{name}</h3>'.format(**category))
            output.append('<table>')
            output.append('  <thead>')
            output.append('    <tr>')
            output.append('      <th>Algorithm</th>')
            output.append('      <th>Modes</th>')
            output.append('      <th>Paddings</th>')
            output.append('      <th>Supported API Levels</th>')
            if show_notes:
                output.append('      <th>Notes</th>')
            output.append('    </tr>')
            output.append('  </thead>')
            output.append('  <tbody>')
            tuples.sort(key=operator.itemgetter(0, 4, 1, 2, 3))
            i = 0
            cur_deprecated = None
            cur_algorithm = None
            cur_mode = None
            while i < len(tuples):
                row = tuples[i]
                if row[4] != cur_deprecated:
                    cur_deprecated = row[4]
                    cur_note = row[5]
                    cur_algorithm = None
                    cur_mode = None
                if cur_deprecated:
                    output.append('    <tr class="deprecated">')
                else:
                    output.append('    <tr>')
                if row[0] != cur_algorithm:
                    cur_algorithm = row[0]
                    cur_mode = None
                    j = i + 1
                    while (j < len(tuples)
                           and tuples[j][4] == cur_deprecated
                           and tuples[j][5] == cur_note
                           and tuples[j][0] == cur_algorithm):
                        j += 1
                    rowspan = j - i
                    if rowspan > 1:
                        output.append('      <td rowspan="%d">%s</td>' % (rowspan, nowrap(cur_algorithm)))
                    else:
                        output.append('      <td>%s</td>' % nowrap(cur_algorithm))
                if row[1] != cur_mode:
                    cur_mode = row[1]
                    j = i + 1
                    while (j < len(tuples)
                           and tuples[j][4] == cur_deprecated
                           and tuples[j][5] == cur_note
                           and tuples[j][0] == cur_algorithm
                           and tuples[j][1] == cur_mode):
                        j += 1
                    rowspan = j - i
                    modestring = '<br>'.join([nowrap(x) for x in cur_mode])
                    if rowspan > 1:
                        output.append('      <td rowspan="%d">%s</td>' % (rowspan, modestring))
                    else:
                        output.append('      <td>%s</td>' % modestring)
                output.append('      <td>%s</td>' % '<br>'.join([nowrap(x) for x in row[2]]))
                output.append('      <td>%s</td>' % nowrap(row[3]))
                if show_notes:
                    output.append('      <td>%s</td>' % row[5])
                output.append('    </tr>')
                i += 1
            output.append('  </tbody>')
            output.append('</table>')
        elif category['name'].endswith('.Supported'):
            # Some categories come with a "Supported" and "Enabled" list, and we
            # group those together in one table for display.  Every entry that's enabled
            # must be supported, so we can just look up the enabled version for each
            # supported item
            basename = category['name'][:-len('.Supported')]
            supported = sort_by_name(category['algorithms'])
            enabled = sort_by_name(find_by_name(categories, basename + '.Enabled')['algorithms'])
            output.append('<h3 id="Supported{0}">{0}</h3>'.format(basename))
            output.append('<table>')
            output.append('  <thead>')
            output.append('    <tr>')
            output.append('      <th>Algorithm</th>')
            output.append('      <th>Supported API Levels</th>')
            output.append('      <th>Enabled By Default</th>')
            if show_notes:
                output.append('      <th>Notes</th>')
            output.append('    </tr>')
            output.append('  </thead>')
            output.append('  <tbody>')
            for algorithm in supported:
                if 'deprecated' in algorithm and algorithm['deprecated']:
                    output.append('    <tr class="deprecated">')
                else:
                    output.append('    <tr>')
                output.append('      <td>%s</td>' % nowrap(algorithm['name']))
                output.append('      <td>%s</td>' % nowrap(algorithm['supported_api_levels']))
                enabled_alg = find_by_name(enabled, algorithm['name'])
                if enabled_alg is None:
                    output.append('      <td></td>')
                else:
                    output.append('      <td>%s</td>' % nowrap(enabled_alg['supported_api_levels']))
                if show_notes:
                    if 'note' in algorithm:
                        output.append('      <td>%s</td>' % algorithm['note'])
                    else:
                        output.append('      <td></td>')
                output.append('    </tr>')
            output.append('  </tbody>')
            output.append('</table>')
        else:
            output.append('<h3 id="Supported{name}">{name}</h3>'.format(**category))
            output.append('<table>')
            output.append('  <thead>')
            output.append('    <tr>')
            output.append('      <th>Algorithm</th>')
            output.append('      <th>Supported API Levels</th>')
            if show_notes:
                output.append('      <th>Notes</th>')
            output.append('    </tr>')
            output.append('  </thead>')
            output.append('  <tbody>')
            algorithms = sort_by_name(category['algorithms'])
            for algorithm in algorithms:
                if 'deprecated' in algorithm and algorithm['deprecated']:
                    output.append('    <tr class="deprecated">')
                else:
                    output.append('    <tr>')
                output.append('      <td>%s</td>' % nowrap(algorithm['name']))
                output.append('      <td>%s</td>' % nowrap(algorithm['supported_api_levels']))
                if show_notes:
                    if 'note' in algorithm:
                        output.append('      <td>%s</td>' % algorithm['note'])
                    else:
                        output.append('      <td></td>')
                output.append('    </tr>')
            output.append('  </tbody>')
            output.append('</table>')
    if args.for_javadoc:
        for i in range(len(output)):
            output[i] = ' * ' + output[i]
    print '\n'.join(output)


if __name__ == '__main__':
    main()
