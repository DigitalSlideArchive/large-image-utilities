import argparse
import pprint
import re

import large_image


def add_to_used(tally, filepath, src, known):
    if '.' not in filepath.rsplit('/', 1)[-1]:
        return
    ext = filepath.rsplit('/', 1)[-1].split('.', 1)[1].strip()
    ext = (ext if '.' not in ext or not any(char.isdigit() for char in ext.rsplit('.')[0]) else
           ext.rsplit('.')[-1])
    ext = ext.lower()
    if '-' in ext or '=' in ext or ' ' in ext:
        return
    if 'corrected.' in ext:
        ext = ext.split('corrected.')[-1]
    if 'shifted.' in ext:
        ext = ext.split('shifted.')[-1]
    if not ext:
        return
    if ext in {'log', 'full', 'safe', '..'}:
        return
    if known and ext in known:
        return
    if src not in tally:
        tally[src] = set()
    tally[src].add(ext)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Compare files read by lisource compare with known extensions of each source.')
    parser.add_argument(
        'compfile', help='An output text file from lisource_compare.')
    parser.add_argument(
        '--no-new', action='store_true',
        help='Do not list extensions that are already associated with any tile source.')
    opts = parser.parse_args()

    compfile = open(opts.compfile).readlines()
    sources = large_image.tilesource.listSources()['sources']
    known = {}
    if opts.no_new:
        known = set(large_image.tilesource.listSources()['extensions'])
    lastsrcline = -2
    lastsrc = ''
    tally = {}
    for lidx, line in enumerate(compfile):
        if not line.strip():
            continue
        if line.startswith('Source'):
            filepath = compfile[lidx - 1]
            continue
        if (line.startswith('Projection: ') or line.startswith('Style: ') or
                line.startswith('mag um')):
            continue
        if line.split()[0] in sources:
            if len([part for part in line.rstrip().split() if re.match(r'\d*\.\d+s', part)]) >= 4:
                lastsrcline = lidx
                lastsrc = line.split()[0]
        if lidx == lastsrcline + 1:
            if len([part for part in line.rstrip().split() if re.match(r'\d{9}', part)]) >= 2:
                add_to_used(tally, filepath, lastsrc, known)
    unlisted = {}
    for src in tally:
        reduced = tally[src] - set(sources[src]['extensions'])
        if reduced:
            unlisted[src] = reduced

    pprint.pprint(unlisted)
