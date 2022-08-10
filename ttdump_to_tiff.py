import argparse
import ast
import math
import re
import tempfile

import tifftools


def adjust_ifds(ifds, tmpfile, lenlist):
    for ifd in ifds:
        maxlen = 0
        for key, record in ifd['tags'].items():
            if 'ifds' in record:
                for ifdlist in record['ifds']:
                    adjust_ifds(ifdlist, tmpfile, lenlist)
            if key in tifftools.Tag and 'bytecount' in tifftools.Tag[key].name.lower():
                maxlen = max(maxlen, max(record['data']))
        off = None
        counts = None
        if tifftools.Tag.StripOffsets.value in ifd['tags']:
            off = ifd['tags'][tifftools.Tag.StripOffsets.value]
            counts = ifd['tags'][tifftools.Tag.StripByteCounts.value]
            w = ifd['tags'][tifftools.Tag.ImageWidth.value]['data'][0]
            h = ifd['tags'][tifftools.Tag.RowsPerStrip.value]['data'][0]
        if tifftools.Tag.TileOffsets.value in ifd['tags']:
            off = ifd['tags'][tifftools.Tag.TileOffsets.value]
            counts = ifd['tags'][tifftools.Tag.TileByteCounts.value]
            w = ifd['tags'][tifftools.Tag.TileWidth.value]['data'][0]
            h = ifd['tags'][tifftools.Tag.TileLength.value]['data'][0]
        if off:
            bps = sum(ifd['tags'][tifftools.Tag.BitsPerSample.value]['data'])
            ifd['tags'][tifftools.Tag.Compression.value]['data'][0] = \
                tifftools.constants.Compression['None'].value
            bytesperchunk = int(math.ceil(w * bps / 8)) * h
            counts['data'] = [bytesperchunk] * len(counts['data'])
            off['data'] = [sum(lenlist)] * len(off['data'])
            maxlen = max(maxlen, bytesperchunk)
        ifd['path_or_fobj'] = tmpfile
        ifd['size'] = sum(lenlist) + maxlen
        lenlist.append(maxlen)
    return lenlist


def write(info, name, destName):
    # For stripbytecounts and tilebytecounts, set compression to none and
    # reclculate size based on strip or tile size
    with tempfile.TemporaryFile() as tmpfile:
        lenlist = adjust_ifds(info['ifds'], tmpfile, [8])
        for idx, count in enumerate(lenlist):
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
            for pos in range(0, count, chunk):
                tmpfile.write(val * min(chunk, count - pos))
        print('%s -> %s' % (name or '', destName))
        tifftools.write_tiff(info, destName, allowExisting=True)


def main(sourceName, destName):  # noqa
    currentName = None
    info = {}
    for line in open(sourceName).readlines():
        line = line.rstrip()
        if line.startswith('-- ') and line.endswith(' --'):
            currentName = line.split('-- ', 1)[1].rsplit(' --', 1)[0]
            continue
        if line.startswith('Header: '):
            if len(info):
                write(info, currentName)
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
        if not tag and not subifd and not tdir:
            continue
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
            elif tag.groups()[4] in {'BYTE', 'UNDEFINED'}:
                record['data'] = ast.literal_eval(tag.groups()[7])
            else:
                count = record['count'] * (2 if 'RATIONAL' in tag.groups()[4] else 1)
                data = [float(v) if tag.groups()[4] in {'FLOAT', 'DOUBELE'} else int(v)
                        for v in tag.groups()[7].split()[:count]
                        if '(' not in v and '...' not in v]
                while len(data) and len(data) < count:
                    data += data
                data = data[:count]
                if (tag.groups()[2] in tifftools.Tag and
                        tifftools.Tag[tag.groups()[2]].isOffsetData()):
                    data = [8] * count
                record['data'] = data
            ifd['tags'][key] = record
    if len(info):
        write(info, currentName, destName)


def command():
    parser = argparse.ArgumentParser(description='Convert a tifftools dump output to a tiff file.')
    parser.add_argument('source', type=str, help='Source tifftools dump filename')
    parser.add_argument('out', type=str, help='Output image filename')
    opts = parser.parse_args()
    main(opts.source, opts.out)


if __name__ == '__main__':
    command()
