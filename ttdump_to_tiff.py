#!/usr/bin/env python3

import argparse
import ast
import math
import re
import tempfile

import tifftools


def adjust_ifds(ifds, tmpfile, lenlist, compression):  # noqa
    for ifd in ifds:
        maxlen = 0
        uncomplen = None
        for key, record in ifd['tags'].items():
            if 'ifds' in record:
                for ifdlist in record['ifds']:
                    adjust_ifds(ifdlist, tmpfile, lenlist, compression)
            if (key in tifftools.Tag and 'bytecount' in tifftools.Tag[key].name.lower() and
                    tifftools.Tag[key].name not in {'StripByteCounts', 'TileByteCounts'}):
                maxlen = max(maxlen, max(record['data']))
        off = None
        counts = None

        if maxlen:
            lenlist.append((maxlen, None))
            maxlen = 0
        if tifftools.Tag.StripOffsets.value in ifd['tags']:
            off = ifd['tags'][tifftools.Tag.StripOffsets.value]
            counts = ifd['tags'][tifftools.Tag.StripByteCounts.value]
            w = ifd['tags'][tifftools.Tag.ImageWidth.value]['data'][0]
            h = ifd['tags'][tifftools.Tag.RowsPerStrip.value]['data'][0]
            h2 = ifd['tags'][tifftools.Tag.ImageLength.value]['data'][0] - (
                ifd['tags'][tifftools.Tag.ImageLength.value]['data'][0] // h) * h or h
        if tifftools.Tag.TileOffsets.value in ifd['tags']:
            off = ifd['tags'][tifftools.Tag.TileOffsets.value]
            counts = ifd['tags'][tifftools.Tag.TileByteCounts.value]
            w = ifd['tags'][tifftools.Tag.TileWidth.value]['data'][0]
            h = ifd['tags'][tifftools.Tag.TileLength.value]['data'][0]
            h2 = h
        if off:
            bps = sum(ifd['tags'][tifftools.Tag.BitsPerSample.value]['data'])
            if tifftools.Tag.Compression.value not in ifd['tags']:
                ifd['tags'][tifftools.Tag.Compression.value] = {
                    'datatype': tifftools.Datatype.SHORT,
                    'count': 1,
                    'data': [0],
                }
            ifd['tags'][tifftools.Tag.Compression.value]['data'][0] = \
                tifftools.constants.Compression['None'].value
            bytesperchunk = int(math.ceil(w * bps / 8)) * h
            if compression == 'packbits':
                ifd['tags'][tifftools.Tag.Compression.value]['data'][0] = \
                    tifftools.constants.Compression.Packbits.value
                uncomplen = bytesperchunk
                bytesperchunk = (uncomplen + 127) // 128 * 2
            counts['data'] = [bytesperchunk] * len(counts['data'])
            off['data'] = [sum(v[0] for v in lenlist)] * len(off['data'])
            maxlen = max(maxlen, bytesperchunk)
            if h2 and h2 != h:
                if len(off['data']) > 1:
                    lenlist.append((maxlen, uncomplen))
                    maxlen = 0
                bytesperchunk = int(math.ceil(w * bps / 8)) * h2
                if compression == 'packbits':
                    uncomplen = bytesperchunk
                    bytesperchunk = (uncomplen + 127) // 128 * 2
                maxlen = max(maxlen, bytesperchunk)
                counts['data'][-1] = bytesperchunk
                off['data'][-1] = sum(v[0] for v in lenlist)
        ifd['path_or_fobj'] = tmpfile
        ifd['size'] = sum(v[0] for v in lenlist) + maxlen
        if maxlen:
            lenlist.append((maxlen, uncomplen))
    return lenlist


def write(info, name, destName, compression):
    # For stripbytecounts and tilebytecounts, set compression to none and
    # reclculate size based on strip or tile size
    with tempfile.TemporaryFile() as tmpfile:
        lenlist = adjust_ifds(info['ifds'], tmpfile, [(8, None)], compression)
        for idx, [count, uncompcount] in enumerate(lenlist):
            val = idx
            if idx:
                rem = 256 - idx
                val = 0
                while rem:
                    val *= 2
                    if rem & 1:
                        val += 1
                    rem >>= 1
            val = val.to_bytes(1, 'little')
            chunk = 65536
            if not uncompcount:
                for pos in range(0, count, chunk):
                    tmpfile.write(val * min(chunk, count - pos))
            else:
                for pos in range(0, uncompcount, chunk * 128):
                    chunklen = min(chunk * 128, uncompcount - pos)
                    rle = (b'\x81' + val) * (chunklen // 128)
                    if chunklen - (chunklen // 128) * 128:
                        rle += (257 - (chunklen - (chunklen // 128) * 128)).to_bytes(
                            1, 'little') + val
                    tmpfile.write(rle)
        print('%s -> %s' % (name or '', destName))
        tifftools.write_tiff(info, destName, allowExisting=True)


def main(sourceName, destName, compression):  # noqa
    currentName = None
    info = {}
    lastascii = None
    isgeo = False
    for line in open(sourceName).readlines():
        line = line.rstrip()
        if line.startswith('-- ') and line.endswith(' --'):
            currentName = line.split('-- ', 1)[1].rsplit(' --', 1)[0]
            continue
        if line.startswith('Header: '):
            if len(info):
                write(info, currentName, compression)
            info = {}
            info['bigEndian'] = 'big-endian' in line
            info['bigtiff'] = 'BigTIFF' in line
            ifd = None
            info['ifds'] = []
            ifdlist = []
            continue
        tdir = re.match(r'^ *Directory ([0-9]+)[,:].*$', line)
        subifd = re.match(r'^ *([0-9a-zA-Z]+):([0-9]+)$', line)
        tag = re.match(
            r'^ *(([^ ]+) |)([0-9]+) \(0x([0-9A-F]+)\) ([A-Z]+[A-Z0-9]*): (<([0-9]+)> |)(.*)$',
            line)
        geotag = re.match(r'^ *([A-Za-z]+): (.*)$', line) if isgeo else None
        if not tag and not subifd and not tdir and not geotag:
            if lastascii:
                lastascii['data'] += '\n' + line
            continue
        lastascii = None
        while not line.startswith('  ' * len(ifdlist)) and len(ifdlist):
            ifdlist = ifdlist[:-1]
        if tdir:
            if not len(ifdlist):
                info['ifds'].append({'tags': {}})
                ifd = info['ifds'][-1]
            else:
                ifdlist[-1].append({'tags': {}})
                ifd = ifdlist[-1][-1]
            ifdlist.append(ifd)
            continue
        if subifd:
            newifd = []
            if tifftools.Tag[subifd.groups()[0]].value not in ifd['tags']:
                ifd['tags'][tifftools.Tag[subifd.groups()[0]].value] = {'ifds': []}
            ifd['tags'][tifftools.Tag[subifd.groups()[0]].value]['ifds'].append(newifd)
            ifd = None
            ifdlist.append(newifd)
            continue
        if tag:
            try:
                key = tifftools.Tag[tag.groups()[2]].value
            except KeyError:
                key = int(tag.groups()[2])
            record = {
                'datatype': tifftools.Datatype[tag.groups()[4]].value,
                'count': int(tag.groups()[6]) if tag.groups()[6] else 1,
            }
            if tag.groups()[4] == 'ASCII':
                record['data'] = tag.groups()[7]
                lastascii = record
            elif tag.groups()[4] in {'BYTE', 'UNDEFINED'}:
                val = tag.groups()[7]
                if "' ..." in val:
                    val = val.rsplit("' ...")[0] + "'"
                if val[:1] == "'":
                    record['data'] = ast.literal_eval(val)
                elif val[:2] == "b'":
                    record['data'] = ast.literal_eval(val)
                else:
                    record['data'] = [int(v) for v in val.split(' ') if v != '...']
            else:
                count = record['count'] * (2 if 'RATIONAL' in tag.groups()[4] else 1)
                data = [float(v) if tag.groups()[4] in {'FLOAT', 'DOUBLE'} else int(v)
                        for v in tag.groups()[7].split()[:count]
                        if '(' not in v and '...' not in v]
                while len(data) and len(data) < count:
                    data += data
                data = data[:count]
                if (tag.groups()[2] in tifftools.Tag and
                        tifftools.Tag[tag.groups()[2]].isOffsetData()):
                    data = [8] * count
                record['data'] = data
            isgeo = key == tifftools.Tag.GeoKeyDirectoryTag.value
            if 'geotag' in ifd and key in {
                    tifftools.Tag.GeoDoubleParamsTag.value,
                    tifftools.Tag.GeoASCIIParamsTag.value}:
                continue
            ifd['tags'][key] = record
        if geotag:
            if 'geotag' not in ifd:
                ifd['geotag'] = [[1, 1, 1, 0], [], '']
            try:
                taginfo = tifftools.constants.GeoTiffGeoKey[geotag.groups()[0]]
            except Exception:
                isgeo = None
                ifd.pop('geotag', None)
                continue
            key = taginfo.value
            if taginfo['datatype'] == tifftools.Datatype.DOUBLE:
                ttype = tifftools.Tag.GeoDoubleParamsTag.value
                val = [float(v) for v in geotag.groups()[1].split()]
                if len(val) == 1 and int(val[0]) == val[0] and val[0] >= -32768 and val[0] <= 32767:
                    ttype, count, offset = 0, 1, int(val[0])
                else:
                    count = len(val)
                    offset = len(ifd['geotag'][1])
                    ifd['geotag'][1].extend(val)
            elif taginfo['datatype'] == tifftools.Datatype.ASCII:
                ttype = tifftools.Tag.GeoASCIIParamsTag.value
                val = geotag.groups()[1] + '|'
                count = len(val)
                offset = len(ifd['geotag'][2])
                ifd['geotag'][2] += val
            else:
                ttype = 0
                count = 1
                offset = int(geotag.groups()[1])
            ifd['geotag'][0].extend([key, ttype, count, offset])
            ifd['geotag'][0][3] += 1
            ifd['tags'][tifftools.Tag.GeoKeyDirectoryTag.value] = {
                'datatype': tifftools.Datatype.SHORT,
                'count': len(ifd['geotag'][0]),
                'data': ifd['geotag'][0]
            }
            if len(ifd['geotag'][1]):
                ifd['tags'][tifftools.Tag.GeoDoubleParamsTag.value] = {
                    'datatype': tifftools.Datatype.DOUBLE,
                    'count': len(ifd['geotag'][1]),
                    'data': ifd['geotag'][1]
                }
            if len(ifd['geotag'][2]):
                ifd['tags'][tifftools.Tag.GeoASCIIParamsTag.value] = {
                    'datatype': tifftools.Datatype.ASCII,
                    'data': ifd['geotag'][2]
                }
    if len(info):
        write(info, currentName, destName, compression)


def command():
    parser = argparse.ArgumentParser(description='Convert a tifftools dump output to a tiff file.')
    parser.add_argument('source', type=str, help='Source tifftools dump filename')
    parser.add_argument('out', type=str, help='Output image filename')
    parser.add_argument(
        '--compression', default='packbits',
        help='One of "packbits", "none" to use for the output.')
    opts = parser.parse_args()
    main(opts.source, opts.out, opts.compression)


if __name__ == '__main__':
    command()
