#!/usr/bin/env python3

# As an example, this is used to compare output over time from
#   lisource_compare.py --all build/tox/externaldata/* > sources.txt
# to see how changes in the large_image library have affected reading the
# default test files

import argparse
import re


def parse_file(path):
    records = {}
    src = None
    with open(path) as fptr:
        lastline = None
        source = None
        style = None
        projection = None
        entry = {'sources': {}, 'first': {}}
        for line in fptr:
            if line.startswith('Source '):
                if source:
                    entry['sources'].pop((style, projection, source))
                if src:
                    records[src] = entry
                source = None
                if lastline:
                    src = lastline
                entry = {'header1': line, 'sources': {}, 'first': {}}
            elif line.startswith('mag '):
                entry['header2'] = line
            elif line.startswith('Style: '):
                style = line
            elif line.startswith('Projection: '):
                projection = line
            elif line[:1] != ' ' and (line[:1] < '0' or line[:1] > '9') and line[:1] != '':
                source = line.split()[0]
                entry['sources'][(style, projection, source)] = {'line1': line}
            else:
                entry['sources'][(style, projection, source)]['line2'] = line
                if re.search(r'\d{9} \d{9}', line) and not (style, projection) in entry['first']:
                    entry['first'][(style, projection)] = source
            lastline = line
        if src:
            records[src] = entry
    return records


def command():  # noqa
    parser = argparse.ArgumentParser(
        description='Compare the outputs of two runs of the the '
        'lisource_compare.py program where non-extended data is reported. '
        'Show diffs when times are significantly different or anything else '
        'has changed.')
    parser.add_argument('file1', help='First text file')
    parser.add_argument('file2', help='Second text file')
    opts = parser.parse_args()
    source1 = parse_file(opts.file1)
    source2 = parse_file(opts.file2)

    records = set(source1.keys()) | set(source2.keys())
    for record in sorted(records):
        if record not in source1:
            print('>%s' % record.rstrip())
            continue
        if record not in source2:
            print('<%s' % record.rstrip())
            continue
        sources = set(source1[record]['sources']) | set(source2[record]['sources'])
        lastprint = None
        if ([e[-1] for e in source1[record]['sources']] !=
                [e[-1] for e in source2[record]['sources']]):
            print(' %s' % record.strip())
            lastprint = False
            print('<order: ' + ','.join(e[-1] for e in source1[record]['sources']))
            print('>order: ' + ','.join(e[-1] for e in source2[record]['sources']))
        firsts = set(source1[record]['first']) | set(source2[record]['first'])
        for style, projection in sorted(firsts):
            if (source1[record]['first'].get((style, projection)) !=
                    source2[record]['first'].get((style, projection))):
                if lastprint is None:
                    print(' %s' % record.strip())
                    lastprint = False
                    if style is not None:
                        print(' %s' % style.rstrip())
                    if projection is not None:
                        print(' %s' % projection.rstrip())
                    print('<first: ' + (source1[record]['first'].get((style, projection)) or ''))
                    print('>first: ' + (source2[record]['first'].get((style, projection)) or ''))
        for style, projection, source in sorted(sources):
            s1 = source1[record]['sources'].get((style, projection, source))
            s2 = source2[record]['sources'].get((style, projection, source))
            diff = s1 is None or s2 is None
            if not diff:
                parts11 = s1['line1'].split()
                parts12 = s1['line2'].split()
                parts21 = s2['line1'].split()
                parts22 = s2['line2'].split()
                for parts1, parts2 in ((parts11, parts21), (parts12, parts22)):
                    diff = diff or len(parts1) != len(parts2)
                    for idx in range(min(len(parts1), len(parts2))):
                        if parts1[idx] != parts2[idx]:
                            if (not re.match(r'\d*\.\d+s', parts1[idx]) or
                                    not re.match(r'\d*\.\d+s', parts2[idx])):
                                diff = True
                            else:
                                time1 = float(parts1[idx][:-1])
                                time2 = float(parts2[idx][:-1])
                                if abs(time1 - time2) > 0.1 and (
                                        time1 / time2 if time2 > time1 else time2 / time1) < 0.5:
                                    diff = diff or ('time1' if time1 > time2 else 'time2')
            if diff:
                if not lastprint:
                    if lastprint is not False:
                        print(' %s' % record.strip())
                    print(' %s' % source1[record]['header1'].rstrip())
                    print(' %s' % source1[record]['header2'].rstrip())
                    lastprint = [-1, -1]
                if lastprint[0] != style:
                    if style is not None:
                        print(' %s' % style.rstrip())
                    lastprint[0] = style
                if lastprint[1] != projection:
                    if projection is not None:
                        print(' %s' % projection.rstrip())
                    lastprint[1] = projection
                diffc = '>' if diff is True else '+' if diff == 'time2' else '-'
                print('<%s' % (s1['line1'].rstrip() if s1 else ''))
                print('<%s' % (s1.get('line2', '').rstrip() if s1 else ''))
                print('%s%s' % (diffc, s2['line1'].rstrip() if s2 else ''))
                print('%s%s' % (diffc, s2.get('line2', '').rstrip() if s2 else ''))


if __name__ == '__main__':
    command()
