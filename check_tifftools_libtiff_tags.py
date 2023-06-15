#!/usr/bin/env python3

import requests
import tifftools

consts = {
    'TIFFTAG': tifftools.constants.Tag,
    'FILETYPE': tifftools.constants.NewSubfileType,
    'OFILETYPE': tifftools.constants.OldSubfileType,
    'COMPRESSION': tifftools.constants.Compression,
    'PHOTOMETRIC': tifftools.constants.Photometric,
    'THRESHOLD': tifftools.constants.Thresholding,
    'FILLORDER': tifftools.constants.FillOrder,
    'ORIENTATION': tifftools.constants.Orientation,
    'PLANARCONFIG': tifftools.constants.PlanarConfig,
    'GROUP3OPT': tifftools.constants.T4Options,
    'GROUP4OPT': tifftools.constants.T6Options,
    'RESUNIT': tifftools.constants.ResolutionUnit,
    'PREDICTOR': tifftools.constants.Predictor,
    'CLEANFAXDATA': tifftools.constants.CleanFaxData,
    'INKSET': tifftools.constants.InkSet,
    'EXTRASAMPLE': tifftools.constants.ExtraSamples,
    'SAMPLEFORMAT': tifftools.constants.SampleFormat,
    'JPEGTABLESMODE': tifftools.constants.JPEGProc,
    'YCBCRPOSITION': tifftools.constants.YCbCrPositioning,
    'EXIFTAG': tifftools.constants.EXIFTag,
    'GPSTAG': tifftools.constants.GPSTag,
}

header = requests.get(
    'https://gitlab.com/libtiff/libtiff/-/raw/master/libtiff/tiff.h?inline=false').text
for key, tagset in consts.items():
    first = True
    for line in header.split('\n'):
        if line.startswith('#define %s_' % key):
            parts = line.split('#define %s_' % key, 1)[1].split()
            name = parts[0]
            altname = name
            if parts[1].lower().startswith('0x'):
                num = int(parts[1], 16)
            else:
                num = int(parts[1])
            if num >= 65536:
                continue
            desc = None
            if '/* ' in line:
                desc = line.split('/* ', 1)[1].split(' */')[0]
            if name.startswith('EP_'):
                altname = name.split('EP_', 1)[1]
            if (name not in tagset and altname not in tagset and
                    name.replace('_', '') not in tagset) or num not in tagset:
                if first:
                    print(key)
                    first = False
                # print(line)
                if not desc:
                    print("    %d: {'name': '%s'}," % (num, altname))
                else:
                    print("    %d: {'name': '%s', 'desc': '%s'}," % (
                        num, altname, desc.lstrip('&')))
