#!/usr/bin/env python3

import argparse
import ast
import json
import math
import pickle
import re
import tempfile

import tifftools


def adjust_ifds(ifds, tmpfile, lenlist, compression):  # noqa
    anySamplesFloat = False
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
            lenlist.append((maxlen, None, anySamplesFloat))
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
            if tifftools.Tag.SampleFormat.value in ifd['tags']:
                anySamplesFloat = anySamplesFloat or (
                    ifd['tags'][tifftools.Tag.SampleFormat.value]['data'][0] not in {1, 2})
            elif (tifftools.Tag.Software.value in ifd['tags'] and
                    'IndicaLabs' in ifd['tags'][tifftools.Tag.Software.value]['data']):
                anySamplesFloat = True
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
                    lenlist.append((maxlen, uncomplen, anySamplesFloat))
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
            lenlist.append((maxlen, uncomplen, anySamplesFloat))
    return lenlist


def set_mcu_starts(path, mcutag, offset, length):
    """
    Find the MCU restart locations and populate tag data with the information.

    :param path: path to the file with JPEG compression.
    :param mcutag: A dictionary whose 'data' value will be set to the list of
        mcu starts.
    :param offset: start of the JPEG in the file.
    :param length: length of the JPEG in the file.
    """
    fptr = open(path, 'rb')
    fptr.seek(offset)
    chunksize = 2 * 1024 ** 2
    mcu = []
    previous = b''
    pos = 0
    while length > 0:
        data = fptr.read(min(length, chunksize))
        if len(data) != min(length, chunksize):
            length = 0
        else:
            length -= len(data)
        data = previous + data
        parts = data.split(b'\xff')
        previous = b'\xff' + parts[-1]
        pos += len(parts[0])
        for part in parts[1:-1]:
            if not len(mcu):
                if part[0] == 0xda:
                    mcu.append(pos + 2 + part[1] * 256 + part[2])
            elif part[0] >= 0xd0 and part[0] <= 0xd7:
                mcu.append(pos + 2)
            pos += 1 + len(part)
    mcutag['data'] = mcu


def convert_to_ndpi(destName):
    import os
    import shutil
    import subprocess

    import pyvips

    with tempfile.TemporaryDirectory() as tempdir:
        info = tifftools.read_tiff(destName)
        for idx, ifd in enumerate(info['ifds']):
            if tifftools.Tag.NDPI_MCU_STARTS.value in ifd['tags']:
                ifdw = ifd['tags'][tifftools.Tag.ImageWidth.value]['data'][0]
                ifdh = ifd['tags'][tifftools.Tag.ImageLength.value]['data'][0]
                jpegPath = os.path.join(tempdir, '_wsi_%d.jpeg' % idx)
                jpegPos = os.path.getsize(destName)
                img = pyvips.Image.tiffload(destName, page=idx)
                img.jpegsave(jpegPath, Q=95, subsample_mode=pyvips.ForeignSubsample.OFF)
                restartInterval = (
                    int(math.ceil(ifdw / 8) * math.ceil(ifdh / 8)) //
                    len(ifd['tags'][tifftools.Tag.NDPI_MCU_STARTS.value]['data']))
                subprocess.check_call(
                    ['jpegtran', '-restart', '%dB' % restartInterval, jpegPath],
                    stdout=open(destName, 'ab'))
                jpegLen = os.path.getsize(destName) - jpegPos
                ifd['tags'][tifftools.Tag.Compression.value]['data'][0] = \
                    tifftools.constants.Compression.JPEG.value
                ifd['tags'][tifftools.Tag.Photometric.value]['data'][0] = \
                    tifftools.constants.Photometric.YCbCr.value
                ifd['tags'][tifftools.Tag.StripOffsets.value]['data'] = [jpegPos]
                ifd['tags'][tifftools.Tag.StripByteCounts.value]['data'] = [jpegLen]
                set_mcu_starts(
                    destName, ifd['tags'][tifftools.Tag.NDPI_MCU_STARTS.value],
                    ifd['tags'][tifftools.Tag.StripOffsets.value]['data'][0],
                    sum(ifd['tags'][tifftools.Tag.StripByteCounts.value]['data']))
        info['size'] = os.path.getsize(destName)
        for ifd in info['ifds']:
            ifd['size'] = info['size']
        tifftools.write_tiff(info, destName + '.ndpi', allowExisting=True)
        shutil.move(destName + '.ndpi', destName)


def write(info, name, destName, compression):
    # For stripbytecounts and tilebytecounts, set compression to none and
    # recalculate size based on strip or tile size
    with tempfile.TemporaryFile() as tmpfile:
        lenlist = adjust_ifds(info['ifds'], tmpfile, [(8, None, False)], compression)
        for idx, [count, uncompcount, onlyZero] in enumerate(lenlist):
            val = idx
            if idx:
                rem = 256 - idx
                val = 0
                while rem:
                    val *= 2
                    if rem & 1:
                        val += 1
                    rem >>= 1
            if onlyZero:
                val = 0
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
        tifftools.write_tiff(info, destName, allowExisting=True, dedup=True, ifdsFirst=True)
    if destName.endswith('.ndpi'):
        convert_to_ndpi(destName)


def generate_imagej_if_needed(info, destName, compression):
    if compression == 'none' and len(info['ifds']) == 1:
        try:
            desc = info['ifds'][0]['tags'][tifftools.Tag.ImageDescription.value]['data']
            if desc.startswith('ImageJ'):
                ijdict = {line.split('=', 1)[0]: line.split('=', 1)[1].strip()
                          for line in desc.split('\n') if '=' in line}
                if int(ijdict['images']) > 1:
                    framelen = sum(info['ifds'][0]['tags'][
                        tifftools.Tag.StripByteCounts.value]['data'])
                    count = framelen * (int(ijdict['images']) - 1)
                    chunk = 65536
                    with open(destName, 'ab') as fptr:
                        for pos in range(0, count, chunk):
                            fptr.write(b'\x00' * min(chunk, count - pos))
        except Exception:
            pass


def parse_ttdump(sourceName, destName, compression):  # noqa
    info = {}
    isgeo = False
    currentName = None
    lastascii = None
    for line in open(sourceName).readlines():
        line = line.rstrip()
        if line.startswith('-- ') and line.endswith(' --'):
            currentName = line.split('-- ', 1)[1].rsplit(' --', 1)[0]
            continue
        if line.startswith('Header: '):
            if len(info):
                write(info, currentName, destName, compression)
                raise Exception('Update destName')
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
                if (len(val) == 1 and int(val[0]) == val[0] and
                        val[0] >= -32768 and val[0] <= 32767):
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
    return info, currentName


def main(sourceName, destName, compression):
    currentName = None
    try:
        info = json.load(open(sourceName, 'r'))
    except Exception:
        try:
            info = pickle.load(open(sourceName, 'rb'))
        except Exception:
            info, currentName = parse_ttdump(sourceName, destName, compression)
    if len(info):
        write(info, currentName, destName, compression)
        generate_imagej_if_needed(info, destName, compression)


def command():
    parser = argparse.ArgumentParser(
        description='Convert a tifftools dump output to a tiff file.  For '
        'minimal size, run "tifftools -y <path> --dedup" after this program.  '
        'For a genuine COG, run "gdalwarp -of COG -CO COMPRESS=LZW -CO '
        'BLOCKSIZE=1024 <src path> <desc path>"')
    parser.add_argument('source', type=str, help='Source tifftools dump filename')
    parser.add_argument('out', type=str, help='Output image filename')
    parser.add_argument(
        '--compression', default='packbits',
        help='One of "packbits", "none" to use for the output.  If trying to '
        'recreate an ImageJ file, use "none".')
    opts = parser.parse_args()
    main(opts.source, opts.out, opts.compression)


if __name__ == '__main__':
    command()
