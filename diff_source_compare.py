#!/usr/bin/env python3

# As an example, this is used to compare output over time from
#   lisource_compare.py --all build/tox/externaldata/* > sources.txt
# to see how changes in the large_image library have affected reading the
# default test files

import argparse
import re
import sys


def command():  # noqa
    parser = argparse.ArgumentParser(
        description='Compare the outputs of two runs of the the '
        'lisource_compare.py program where non-extended data is reported. '
        'Show diffs when times are significantly different or anything else '
        'has changed.')
    parser.add_argument('file1', help='First text file')
    parser.add_argument('file2', help='Second text file')
    opts = parser.parse_args()
    f1 = open(opts.file1)
    f2 = open(opts.file2)
    source1 = None
    source2 = None
    # style1 = None
    # style2 = None
    # projection1 = None
    # projection2 = None
    line1 = None
    line2 = None
    diffsource = None
    diff1 = []
    diff2 = []
    even = False
    diff = False
    lastdiff = False
    while True:
        lastline1 = line1
        lastline2 = line2
        lastdiff = diff
        try:
            line1 = next(f1)
        except Exception:
            line1 = None
        try:
            line2 = next(f2)
        except Exception:
            line2 = None
        if not line1 and not line2:
            break
        even = not even
        line1 = line1 or ''
        line2 = line2 or ''
        if line1.startswith('Source '):
            source1 = lastline1
            sys.stdout.write(''.join(diff1) + ''.join(diff2))
            diff1 = []
            diff2 = []
            diffsource = None
            even = True
        if line2.startswith('Source '):
            source2 = lastline2
            sys.stdout.write(''.join(diff1) + ''.join(diff2))
            diff1 = []
            diff2 = []
            diffsource = None
        if line1.startswith('Style: '):
            # style1 = lastline1
            sys.stdout.write(''.join(diff1) + ''.join(diff2))
            diff1 = []
            diff2 = []
            diffsource = None
        if line2.startswith('Style: '):
            # style2 = lastline2
            sys.stdout.write(''.join(diff1) + ''.join(diff2))
            diff1 = []
            diff2 = []
            diffsource = None
        if line1.startswith('Projection: '):
            # projection1 = lastline1
            sys.stdout.write(''.join(diff1) + ''.join(diff2))
            diff1 = []
            diff2 = []
            diffsource = None
        if line2.startswith('Projection: '):
            # projection2 = lastline2
            sys.stdout.write(''.join(diff1) + ''.join(diff2))
            diff1 = []
            diff2 = []
            diffsource = None
        diff = False
        if line1 != line2:
            parts1 = line1.split()
            parts2 = line2.split()
            if len(parts1) != len(parts2):
                diff = True
            else:
                for idx in range(len(parts1)):
                    if parts1[idx] != parts2[idx]:
                        if (not re.match(r'\d+\.\d+s', parts1[idx]) or
                                not re.match(r'\d+\.\d+s', parts2[idx])):
                            diff = True
                        else:
                            time1 = float(parts1[idx][:-1])
                            time2 = float(parts2[idx][:-1])
                            if abs(time1 - time2) > 0.1 and (
                                    time1 / time2 if time2 > time1 else time2 / time1) < 0.5:
                                diff = True
        if diff and not diffsource:
            if source1 != source2:
                diff1.append('<%s\n' % source1.rstrip())
                diff2.append('>%s\n' % source2.rstrip())
            else:
                diff1.append(' %s\n' % source1.rstrip())
            diffsource = source1, source2
        if diff:
            if not even and not lastdiff:
                diff1.append('<%s\n' % lastline1.rstrip())
                diff2.append('>%s\n' % lastline2.rstrip())
            diff1.append('<%s\n' % line1.rstrip())
            diff2.append('>%s\n' % line2.rstrip())
    sys.stdout.write(''.join(diff1) + ''.join(diff2))


if __name__ == '__main__':
    command()
