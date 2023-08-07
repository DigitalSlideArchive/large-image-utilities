#!/usr/bin/env python3

import argparse
import itertools
import sys
import time

import h5py
import numpy as np

# Inspired from https://stackoverflow.com/a/43374773


def scan_node(src, dest=None, analyze=False, showattrs=False, convert=None, exclude=None, indent=0):  # noqa
    if exclude and src.name in exclude:
        return
    print('%s%s' % ('  ' * indent, src.name))
    for ak in src.attrs:
        if showattrs:
            print('%s:%s: %r' % ('  ' * indent, ak, src.attrs[ak]))
        if dest:
            dest.attrs[ak] = src.attrs[ak]
    for k, v in src.items():
        if exclude and v.name in exclude:
            continue
        if isinstance(v, h5py.Dataset):
            print('%s - %s %s %r %r %s' % (
                '  ' * (indent + 1), v.name, v.dtype, v.shape,
                v.chunks, v.compression))
            if showattrs:
                for ak in v.attrs:
                    print('%s   :%s: %r' % ('  ' * (indent + 1), ak, v.attrs[ak]))
            lasttime = time.time()
            if v.dtype.kind in {'f', 'i'} and analyze:
                minv = maxv = None
                sumv = 0
                for coor in itertools.product(*(
                        range(0, v.shape[idx], v.chunks[idx]) for idx in range(len(v.shape)))):
                    field = tuple(
                        slice(coor[idx], min(coor[idx] + v.chunks[idx], v.shape[idx]))
                        for idx in range(len(v.shape)))
                    part = v[field]
                    if minv is None:
                        minv = np.amin(part)
                        maxv = np.amax(part)
                    else:
                        minv = min(minv, np.amin(part))
                        maxv = max(maxv, np.amax(part))
                    if part.dtype == np.float16:
                        part = part.astype(np.float32)
                    sumv += part.sum()
                avgv = sumv / v.size
                print('%s   [%g,%g] %g' % (
                    '  ' * (indent + 1), minv, maxv, avgv))
            if dest:
                conv = convert and (v.dtype == np.float64 or (
                    v.dtype == np.float32 and convert == 'float16'))
                if conv:
                    conv = np.float32 if convert == 'float32' or max(
                        abs(minv), maxv) >= 65504 else np.float16
                    if conv == v.dtype:
                        conv = False
                if conv:
                    destv = dest.create_dataset(
                        k, shape=v.shape,
                        dtype=conv,
                        chunks=True, fillvalue=0,
                        compression='gzip', compression_opts=9, shuffle=True)
                else:
                    destv = dest.create_dataset(
                        k, shape=v.shape,
                        dtype=v.dtype,
                        chunks=True, fillvalue=v.fillvalue,
                        compression='gzip', compression_opts=9, shuffle=v.shuffle)
                for ak in v.attrs:
                    destv.attrs[ak] = v.attrs[ak]
                steps = len(list(itertools.product(*(
                    range(0, v.shape[idx], destv.chunks[idx])
                    for idx in range(len(v.shape))))))
                skip = 0
                for cidx, coor in enumerate(itertools.product(*(
                        range(0, v.shape[idx], destv.chunks[idx])
                        for idx in range(len(v.shape))))):
                    if time.time() - lasttime > 10:
                        sys.stdout.write('  %5.2f%% %r %r %r\r' % (
                            100.0 * cidx / steps, coor, v.shape, destv.chunks))
                        sys.stdout.flush()
                        lasttime = time.time()
                    field = tuple(
                        slice(coor[idx], min(coor[idx] + destv.chunks[idx], v.shape[idx]))
                        for idx in range(len(v.shape)))
                    part = v[field]
                    if conv:
                        if not part.any():
                            skip += 1
                            continue
                        part = part.astype(conv)
                    destv[field] = part
                print('%s > %s %s %r %r %s%s' % (
                    '  ' * (indent + 1), destv.name, destv.dtype, destv.shape,
                    destv.chunks, destv.compression,
                    ' %d' % skip if skip else ''))

        elif isinstance(v, h5py.Group):
            destv = None
            if dest:
                destv = dest.create_group(k)
            scan_node(v, destv, analyze, showattrs, convert, exclude, indent=indent + 1)


def scan_hdf5(path, analyze=False, showattrs=False, outpath=None, convert=None, exclude=None):
    if convert:
        analyze = True
    with h5py.File(path, 'r') as fptr:
        fptr2 = None
        if outpath:
            fptr2 = h5py.File(outpath, 'w')
        scan_node(fptr, fptr2, analyze, showattrs, convert, exclude)


def command():
    parser = argparse.ArgumentParser(
        description='Scan an hdf5 file and report on its groups, datasets, '
        'and attributes.  Optionally report mininum, maximum, and average '
        'values for datasets with integer or float datatypes.  Optionally '
        'rewrite the file with lower precision float datasets.')
    parser.add_argument(
        'source', type=str, help='Source file to read and analyze.')
    parser.add_argument(
        '--analyze', '-s', action='store_true',
        help='Analyze the min/max/average of datasets.')
    parser.add_argument(
        '--attrs', '-k', action='store_true',
        help='Show attributes on groups and datasets.')
    parser.add_argument(
        '--dest', help='Write a new output file')
    parser.add_argument(
        '--convert', choices=('float16', 'float32'),
        help='Reduce the precision of the output file.')
    parser.add_argument(
        '--exclude', action='append',
        help='Exclude a dataset or group from the output file.')
    opts = parser.parse_args()
    scan_hdf5(opts.source, opts.analyze, opts.attrs, opts.dest, opts.convert, opts.exclude)


if __name__ == '__main__':
    command()
