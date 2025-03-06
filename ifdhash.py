import hashlib
import pprint
import sys

import tifftools


def hash_ifd(idx, ifd, tagSet=tifftools.Tag, collect=None):
    if collect is None:
        collect = {}
    subifdList = []
    offsets = counts = None
    for tag, taginfo in sorted(ifd['tags'].items()):
        tag = tifftools.constants.get_or_create_tag(
            tag, tagSet, {'datatype': tifftools.constants.Datatype[taginfo['datatype']]})
        if tag.isIFD() or taginfo['datatype'] in (tifftools.constants.Datatype.IFD,
                                                  tifftools.constants.Datatype.IFD8):
            subifdList.append((tag, taginfo))
        elif tag.value in (tifftools.Tag.TileOffsets.value, tifftools.Tag.StripOffsets.value):
            offsets = taginfo['data']
        elif tag.value in (tifftools.Tag.TileByteCounts.value, tifftools.Tag.StripByteCounts.value):
            counts = taginfo['data']
    if offsets and counts and len(offsets) == len(counts):
        with tifftools.path_or_fobj.OpenPathOrFobj(ifd['path_or_fobj'], 'rb') as fptr:
            m = hashlib.sha512()
            for oidx, offset in enumerate(offsets):
                if offset and counts[oidx]:
                    fptr.seek(offset)
                    m.update(fptr.read(counts[oidx]))
            collect[tuple(idx)] = m.hexdigest()
    for tag, taginfo in subifdList:
        for subidx, subifds in enumerate(taginfo['ifds']):
            for ssidx, sifd in enumerate(subifds):
                hash_ifd(idx + [subidx, ssidx], sifd, getattr(tag, 'tagset', None), collect)
    return collect


def hash_tifffile(path):
    collect = {}
    info = tifftools.read_tiff(path)
    for idx, ifd in enumerate(info['ifds']):
        hash_ifd([idx], ifd, collect=collect)
        break  # ##DWM::
    return collect


result = hash_tifffile(sys.argv[1])
print(result[(0,)], sys.argv[1])
# pprint.pprint(result)
