#!/usr/bin/env python3

import argparse
import itertools
import math
import os
import pprint

import numpy as np
import zarr


def show_attrs(src, indent):
    for ak in src.attrs:
        if isinstance(src.attrs[ak], (dict, list)):
            form = pprint.pformat(src.attrs[ak], compact=True, width=80 - (
                indent + 2) * 2).strip().split('\n')
            if len(form) > 1:
                print('%s:%s:' % ('  ' * indent, ak))
                for line in form:
                    print('%s%s' % ('  ' * (indent + 2), line))
            else:
                print('%s:%s: %s' % ('  ' * indent, ak, form[0]))
        else:
            print('%s:%s: %r' % ('  ' * indent, ak, src.attrs[ak]))


def scan_dataset(v, analyze, showattrs, sample, indent):
    minv = maxv = None
    print('%s - %s %s %r %r %s' % (
        '  ' * (indent + 1), v.name, v.dtype, v.shape,
        v.chunks, v.compressor.cname))
    if showattrs:
        show_attrs(v, indent + 1)
    if v.dtype.kind in {'f', 'i', 'u'} and analyze:
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
    if sample and len(v.shape) == 1:
        checksize = int(math.ceil(v.shape[0] ** 0.5))
        sampleset = np.unique(v[:min(v.shape[0], checksize * 2)])
        if len(sampleset) < checksize:
            sampleset = dict(zip(*np.unique(v, return_counts=True)))
            sampleset = {k: val for val, k in sorted([
                (val, k) for k, val in sampleset.items()], reverse=True)}
            if len(sampleset) < max(10, checksize):
                print('%s   [%d kinds] %r' % (
                    '  ' * (indent + 1), len(sampleset),
                    {k: sampleset[k] for k in itertools.islice(sampleset, 100)}))
    return minv, maxv


def scan_node(src, analyze=False, showattrs=False, sample=False, indent=0):
    print('%s%s' % ('  ' * indent, src.name))
    if showattrs:
        show_attrs(src, indent)
    for _k, v in src.items():
        if isinstance(v, zarr.core.Array):
            minv, maxv = scan_dataset(v, analyze, showattrs, sample, indent)
        elif isinstance(v, zarr.hierarchy.Group):
            scan_node(v, analyze, showattrs, sample, indent=indent + 1)


def scan_zarr(path, analyze=False, showattrs=False, sample=False):
    if os.path.isdir(path):
        if (not os.path.exists(os.path.join(path, '.zgroup')) and
                not os.path.exists(os.path.join(path, '.zattrs'))):
            print(f'Cannot parse {path}')
            return
    try:
        fptr = zarr.open(zarr.SQLiteStore(str(path)))
    except Exception:
        try:
            fptr = zarr.open(path)
        except Exception:
            print(f'Cannot parse {path}')
            return
    scan_node(fptr, analyze, showattrs, sample)


def command():
    parser = argparse.ArgumentParser(
        description='Scan a zarr file or directory and report on its groups, '
        'datasets, and attributes.  Optionally report mininum, maximum, and '
        'average values for datasets with integer or float datatypes.')
    parser.add_argument(
        'source', type=str, help='Source file to read and analyze.')
    parser.add_argument(
        '--analyze', '-s', action='store_true',
        help='Analyze the min/max/average of datasets.')
    parser.add_argument(
        '--sample', action='store_true',
        help='Show a sample of 1-d data sets if they have fewer unique values '
        'than the square root of their size.')
    parser.add_argument(
        '--attrs', '-k', action='store_true',
        help='Show attributes on groups and datasets.')
    opts = parser.parse_args()
    print(opts.source)
    scan_zarr(opts.source, opts.analyze, opts.attrs, opts.sample)


if __name__ == '__main__':
    command()
