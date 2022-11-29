#!/usr/bin/env python3

import argparse
import glob
import os
import sys

import large_image

os.environ['GDAL_PAM_ENABLED'] = 'NO'
os.environ['CPL_LOG'] = os.devnull

format = '%6d %6d %5d %5d %6.3f %6d%5d%5d%5d%5d%12d %-10s %s\n'


def main(opts):
    sys.stdout.write(
        ' Width Height TileW TileH um/pix Frames    C    Z    T   XY'
        '        size format     name\n')
    for source in opts.source:
        for sourcePath in sorted(glob.glob(source)):
            source_check(sourcePath, opts)


def source_check(sourcePath, opts):  # noqa
    try:
        li = large_image.open(sourcePath)
    except Exception:
        sys.stdout.write('%-82s %s\n' % ('-- not a large image --', sourcePath))
        sys.stdout.flush()
        return
    metadata = li.getMetadata()
    sys.stdout.write(format % (
        metadata['sizeX'],
        metadata['sizeY'],
        metadata['tileWidth'],
        metadata['tileHeight'],
        (metadata.get('mm_x', 0) or 0) * 1000,
        len(metadata.get('frames', [])) or 1,
        metadata.get('IndexRange', {}).get('IndexC', 0) or 1,
        metadata.get('IndexRange', {}).get('IndexZ', 0) or 1,
        metadata.get('IndexRange', {}).get('IndexT', 0) or 1,
        metadata.get('IndexRange', {}).get('IndexXY', 0) or 1,
        os.path.getsize(sourcePath),
        li.name,
        sourcePath,
    ))
    sys.stdout.flush()


def command():
    parser = argparse.ArgumentParser(
        description='Report some basic metadata about large images.')
    parser.add_argument(
        'source', nargs='+', type=str,
        help='Source file to read and analyze')
    opts = parser.parse_args()
    main(opts)


if __name__ == '__main__':
    command()
