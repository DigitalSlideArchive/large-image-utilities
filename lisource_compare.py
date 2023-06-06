#!/usr/bin/env python3

import argparse
import glob
import itertools
import logging
import math
import os
import pprint
import sys
import time

import large_image
import numpy

os.environ['GDAL_PAM_ENABLED'] = 'NO'
os.environ['CPL_LOG'] = os.devnull


def histotext(h, maxchan=None):
    ctbl = '0123456789'
    hist = None
    for entry in h['histogram'][:maxchan or len(h['histogram'])]:
        if hist is None:
            hist = entry['hist'].tolist().copy()
        else:
            for idx, val in enumerate(entry['hist'].tolist()):
                hist[idx] += val
    maxval = max(hist) or 1
    result = ''
    for val in hist:
        scale = int(min(len(ctbl) - 1, math.floor(len(ctbl) * val / maxval)))
        result += ctbl[scale]
    return result


def write_thumb(img, source, prefix, name, opts=None, idx=None, idx2=None):
    if not prefix or not img:
        return
    ext = 'jpg' if not opts or not opts.encoding else opts.encoding.lower()
    idxStr = '' if not idx else '-%s' % str(idx)
    idx2Str = '' if not idx2 and not idx else '-%s' % str(idx2)
    path = '%s-%s-%s%s%s.%s' % (prefix, name, source, idxStr, idx2Str, ext)
    open(path, 'wb').write(img)


def float_format(val, length):
    s = ('%.' + str(length) + 'f') % val
    while ('.' in s and s[-1] == '0') or s[-1] == '.':
        s = s[:-1]
    if '.' in s and s.index('.') >= length - 1:
        s = s[:s.index('.')]
    if '.' in s:
        s = s[:length]
    elif len(s) > length:
        exp = 1
        while len(s) - (length - 1 - exp) >= 10 ** exp:
            exp += 1
        s = s[:length - 1 - exp] + 'e' + '%d' % (len(s) - (length - 1 - exp))
    if len(s) < length:
        s = ' ' * (length - len(s)) + s
    return s


def main(opts):
    sources = sorted([sourcePath
                      for source in opts.source
                      for sourcePath in sorted(glob.glob(source))
                      ])
    sources += sorted([source for source in opts.source
                       if source.startswith('https://') or source.startswith('http://')])
    for sourcePath in sources:
        source_compare(sourcePath, opts)


def source_compare(sourcePath, opts):  # noqa
    sys.stdout.write('%s\n' % sourcePath)
    sys.stdout.flush()
    canread = large_image.canReadList(sourcePath)
    large_image.cache_util.cachesClear()
    slen = max([len(source) for source, _ in canread] + [10])
    sys.stdout.write('Source' + ' ' * (slen - 6))
    sys.stdout.write('  Width Height')
    sys.stdout.write(' Fram')
    sys.stdout.write(' thumbnail')
    sys.stdout.write('    tile 0')
    sys.stdout.write('    tile n')
    sys.stdout.write('  tile f 0')
    sys.stdout.write('  tile f n')
    sys.stdout.write('\n')
    sys.stdout.write('%s' % (' ' * (slen - 10)))
    sys.stdout.write('mag um/pix')
    sys.stdout.write('  TileW  TileH')
    sys.stdout.write(' dtyp')
    sys.stdout.write(' Histogram')
    sys.stdout.write(' Histogram')
    sys.stdout.write(' Histogram' if opts.full else '          ')
    sys.stdout.write(' Histogram')
    sys.stdout.write(' Histogram' if opts.full else '          ')
    sys.stdout.write('\n')
    if opts.histlevels:
        sys.stdout.write('Lvl Fram Histogram                       ')
        sys.stdout.write(' Min    Max    Mean   Stdev  Time     ')
        sys.stdout.write('\n')

    thumbs = opts.thumbs
    if thumbs and os.path.isdir(thumbs):
        thumbs = os.path.join(thumbs, 'compare-' + os.path.basename(sourcePath))
    kwargs = {}
    if opts.encoding:
        kwargs['encoding'] = opts.encoding
    styles = [None if val == '' else val for val in (opts.style or [None])]
    projections = [None if val == '' else val for val in (opts.projection or [None])]
    for (styleidx, style), (projidx, projection) in itertools.product(
            enumerate(styles), enumerate(projections)):
        kwargs['style'] = style
        if style is None:
            kwargs.pop('style', None)
        if len(styles) > 1:
            sys.stdout.write('Style: %s\n' % (str(style)[:72]))
        kwargs['projection'] = projection
        if projection is None:
            kwargs.pop('projection', None)
        if len(projections) > 1:
            sys.stdout.write('Projection: %s\n' % (str(projection)[:72]))
        for source, couldread in canread:
            if getattr(opts, 'skipsource', None) and source in opts.skipsource:
                continue
            if getattr(opts, 'usesource', None) and source not in opts.usesource:
                continue
            if projection and not getattr(
                    large_image.tilesource.AvailableTileSources[source],
                    '_geospatial_source', None):
                continue
            sys.stdout.write('%s' % (source + ' ' * (slen - len(source))))
            sys.stdout.flush()
            try:
                ts = large_image.tilesource.AvailableTileSources[source](sourcePath, **kwargs)
            except Exception as exp:
                sexp = str(exp).replace('\n', ' ').replace('  ', ' ').strip()
                sexp = sexp.replace(sourcePath, '<path>')
                sys.stdout.write(' %s\n' % sexp[:78 - slen])
                sys.stdout.write('%s %s\n' % (' ' * slen, sexp[78 - slen: 2 * (78 - slen)]))
                sys.stdout.flush()
                continue
            sys.stdout.write(' %6d %6d' % (ts.sizeX, ts.sizeY))
            sys.stdout.flush()
            try:
                metadata = ts.getMetadata()
            except Exception as exp:
                sexp = str(exp).replace('\n', ' ').replace('  ', ' ').strip()
                sexp = sexp.replace(sourcePath, '<path>')
                sys.stdout.write(' %s\n' % sexp[:64 - slen])
                sys.stdout.write('%s %s\n' % (
                    ' ' * slen if not couldread else ' canread' + ' ' * (slen - 8),
                    sexp[59 - slen: (59 - slen) + (78 - slen)]))
                sys.stdout.flush()
                continue
            frames = len(metadata.get('frames', [])) or 1
            levels = metadata['levels']
            tx0 = ty0 = tz0 = 0
            hx = ts.sizeX // ts.tileWidth // 2
            hy = ts.sizeY // ts.tileHeight // 2
            if projection and 'bounds' in metadata:
                kwargs['region'] = dict(
                    left=metadata['bounds']['xmin'],
                    top=metadata['bounds']['ymin'],
                    right=metadata['bounds']['xmax'],
                    bottom=metadata['bounds']['ymax'],
                    units='projection')
                grb = ts._getRegionBounds(metadata, **kwargs.get('region', {}))
                for level in range(metadata['levels']):
                    if (((grb[0] + 1) // 2 ** level // metadata['tileWidth'] ==
                         grb[2] // 2 ** level // metadata['tileWidth']) and
                        ((grb[1] + 1) // 2 ** level // metadata['tileHeight'] ==
                         grb[3] // 2 ** level // metadata['tileHeight'])):
                        tz0 = metadata['levels'] - 1 - level
                        tx0 = grb[0] // 2 ** level // metadata['tileWidth']
                        ty0 = grb[1] // 2 ** level // metadata['tileWidth']
                        hx = (grb[0] + grb[2]) // 2 // metadata['tileWidth']
                        hy = (grb[1] + grb[3]) // 2 // metadata['tileWidth']
                        break
            sys.stdout.write('%5d' % frames)
            sys.stdout.flush()
            t = time.time()
            try:
                img = ts.getThumbnail(**kwargs)
            except Exception as exp:
                sexp = str(exp).replace('\n', ' ').replace('  ', ' ').strip()
                sexp = sexp.replace(sourcePath, '<path>')
                sys.stdout.write(' %s\n' % sexp[:59 - slen])
                sys.stdout.write('%s %s\n' % (
                    ' ' * slen if not couldread else ' canread' + ' ' * (slen - 8),
                    sexp[59 - slen: (59 - slen) + (78 - slen)]))
                sys.stdout.flush()
                continue
            thumbtime = time.time() - t
            sys.stdout.write(' %8.3fs' % thumbtime)
            sys.stdout.flush()
            write_thumb(img[0], source, thumbs, 'thumbnail', opts, styleidx, projidx)
            t = time.time()
            img = ts.getTile(tx0, ty0, tz0, sparseFallback=True)
            tile0time = time.time() - t
            sys.stdout.write(' %8.3fs' % tile0time)
            sys.stdout.flush()
            write_thumb(img, source, thumbs, 'tile0', opts, styleidx, projidx)
            t = time.time()
            img = ts.getTile(hx, hy, levels - 1, sparseFallback=True)
            tilentime = time.time() - t
            sys.stdout.write(' %8.3fs' % tilentime)
            sys.stdout.flush()
            write_thumb(img, source, thumbs, 'tilen', opts, styleidx, projidx)
            if frames > 1:
                t = time.time()
                img = ts.getTile(0, 0, 0, frame=frames - 1, sparseFallback=True)
                tilef0time = time.time() - t
                sys.stdout.write(' %8.3fs' % tilef0time)
                sys.stdout.flush()
                write_thumb(img, source, thumbs, 'tilef0', opts, styleidx, projidx)
                t = time.time()
                img = ts.getTile(hx, hy, levels - 1, frame=frames - 1, sparseFallback=True)
                tilefntime = time.time() - t
                sys.stdout.write(' %8.3fs' % tilefntime)
                sys.stdout.flush()
                write_thumb(img, source, thumbs, 'tilefn', opts, styleidx, projidx)
            sys.stdout.write('\n')

            if not couldread:
                sys.stdout.write(' !canread' + (' ' * (slen - 9)))
            else:
                sys.stdout.write(' ' * (slen - 10))
                sys.stdout.write('%3s ' % (
                    ('%3.1f' % metadata['magnification'])[:3].rstrip('.')
                    if metadata.get('magnification') else ''))
                um = (metadata.get('mm_x', 0) or 0) * 1000
                umstr = '      '
                if um and um < 100:
                    umstr = '%6.3f' % um
                elif um:
                    prefix = 'um kM'
                    val = um
                    idx = 0
                    while val >= 10000 and idx + 1 < len(prefix):
                        idx += 1
                        val /= 1000
                    umstr = '%4.0f%sm' % (val, prefix[idx])
                sys.stdout.write(umstr)
            sys.stdout.write(' %6d %6d' % (ts.tileWidth, ts.tileHeight))
            if hasattr(ts, 'dtype'):
                sys.stdout.write(' %4s' % numpy.dtype(ts.dtype).str.lstrip('|').lstrip('<')[:4])
            else:
                sys.stdout.write('     ')
            sys.stdout.flush()

            # get maxval for other histograms
            h = ts.histogram(onlyMinMax=True, output=dict(maxWidth=2048, maxHeight=2048), **kwargs)
            maxval = max(h['max'].tolist())
            maxval = 2 ** (int((math.log(maxval or 1) / math.log(2))) + 1) if maxval > 1 else 1
            # thumbnail histogram
            h = ts.histogram(bins=9, output=dict(maxWidth=256, maxHeight=256),
                             range=[0, maxval], **kwargs)
            maxchan = len(h['histogram'])
            if maxchan == 4:
                maxchan = 3
            sys.stdout.write(' %s' % histotext(h, maxchan))
            sys.stdout.flush()
            # full image histogram
            h = ts.histogram(bins=9, output=dict(maxWidth=2048, maxHeight=2048),
                             range=[0, maxval], **kwargs)
            sys.stdout.write(' %s' % histotext(h, maxchan))
            sys.stdout.flush()
            if opts.full:
                # at full res
                h = ts.histogram(bins=9, range=[0, maxval], **kwargs)
                sys.stdout.write(' %s' % histotext(h, maxchan))
                sys.stdout.flush()
            else:
                sys.stdout.write(' %s' % (' ' * 9))
            if frames > 1:
                # last frame full image histogram
                h = ts.histogram(
                    bins=9, output=dict(maxWidth=2048, maxHeight=2048),
                    range=[0, maxval], frame=frames - 1, **kwargs)
                sys.stdout.write(' %s' % histotext(h, maxchan))
                sys.stdout.flush()
                if opts.full:
                    # at full res
                    h = ts.histogram(bins=9, range=[0, maxval], frame=frames - 1, **kwargs)
                    sys.stdout.write(' %s' % histotext(h, maxchan))
                    sys.stdout.flush()
                else:
                    sys.stdout.write(' %s' % (' ' * 9))
            sys.stdout.write('\n')
            if opts.histlevels:
                # histograms at all levels aon the first and last frames
                for f in range(0, frames, (frames - 1) or 1):
                    for ll in range(levels):
                        t = -time.time()
                        h = ts.histogram(bins=32, output=dict(
                            maxWidth=int(math.ceil(ts.sizeX / 2 ** (levels - 1 - ll))),
                            maxHeight=int(math.ceil(ts.sizeY / 2 ** (levels - 1 - ll)))
                        ), range=[0, maxval], frame=f, **kwargs)
                        t += time.time()
                        sys.stdout.write('%3d%5d %s' % (ll, f, histotext(h, maxchan)))
                        sys.stdout.write(' %s %s %s %s' % (
                            float_format(min(h['min'].tolist()[:maxchan]), 6),
                            float_format(max(h['max'].tolist()[:maxchan]), 6),
                            float_format(sum(h['mean'].tolist()[:maxchan]) / maxchan, 6),
                            float_format(sum(h['stdev'].tolist()[:maxchan]) / maxchan, 6)))
                        sys.stdout.write(' %8.3fs' % t)
                        sys.stdout.write('\n')
                        sys.stdout.flush()
            if opts.metadata:
                sys.stdout.write(pprint.pformat(ts.getMetadata()).strip() + '\n')
            if opts.internal:
                sys.stdout.write(pprint.pformat(ts.getInternalMetadata()).strip() + '\n')
            if opts.assoc:
                sys.stdout.write(pprint.pformat(ts.getAssociatedImagesList()).strip() + '\n')
                for assoc in ts.getAssociatedImagesList():
                    img = ts.getAssociatedImage(assoc, **kwargs)
                    write_thumb(img[0], source, thumbs, 'assoc-%s' % assoc, opts, styleidx, projidx)


def command():
    parser = argparse.ArgumentParser(
        description='Compare each large_image source on how it reads a file.  '
        'For each source, times are measured to read the thumbnail, the '
        'singular tile at zero level, the center tile at maximum level (all '
        'for frame 0), the singular at zero and center at maximum tiles for '
        'the last frame for multiframe files.  A histogram is computed for '
        'the thumbnail and the singular tile(s) and, optionally, the whole '
        'image at the maximum level (which is slow).')
    parser.add_argument(
        'source', nargs='+', type=str,
        help='Source file to read and analyze')
    parser.add_argument(
        '--usesource', '--use', action='append',
        help='Only use the specified source.  Can be specified multiple times.')
    parser.add_argument(
        '--skipsource', '--skip', action='append',
        help='Do not use the specified source.  Can be specified multiple '
        'times.')
    parser.add_argument('--full', action='store_true', help='Run histogram on full image')
    parser.add_argument(
        '--histogram-levels', '--hl', action='store_true', dest='histlevels',
        help='Run histogram on each level')
    parser.add_argument(
        '--all', action='store_true',
        help='All sources to read all files.  Otherwise, some sources avoid '
        'some files based on name.')
    parser.add_argument(
        '--thumbs', '--thumbnails', type=str, required=False,
        help='Location to write thumbnails of results.  If this is not an '
        'existing directory, it is a prefix for the resultant files.')
    parser.add_argument(
        '--metadata', action='store_true',
        help='Print metadata from the file.')
    parser.add_argument(
        '--internal', action='store_true',
        help='Print internal metadata from the file.')
    parser.add_argument(
        '--assoc', '--associated', action='store_true',
        help='List associated images from the file.')
    parser.add_argument(
        '--encoding', help='Optional encoding for tiles (e.g., PNG)')
    # TODO append this to a list to allow multiple encodings tested
    parser.add_argument(
        '--style', action='append',
        help='Use the json style when testing.  Can be specified multiple times.')
    parser.add_argument(
        '--projection', action='append',
        help='Use the projection when testing.  Can be specified multiple '
        'times.  EPSG:3857 is a common choice.')
    # TODO add a flag to skip non-geospatial sources if a projection is used
    parser.add_argument(
        '--verbose', '-v', action='count', default=0, help='Increase verbosity')
    parser.add_argument(
        '--silent', '-s', action='count', default=0, help='Decrease verbosity')
    opts = parser.parse_args()
    li_logger = large_image.config.getConfig('logger')
    li_logger.setLevel(max(1, logging.CRITICAL - (opts.verbose - opts.silent) * 10))
    li_logger.addHandler(logging.StreamHandler(sys.stderr))
    if not large_image.tilesource.AvailableTileSources:
        large_image.tilesource.loadTileSources()
    if opts.all:
        for key in list(large_image.config.ConfigValues):
            if '_ignored_names' in key:
                del large_image.config.ConfigValues[key]
    main(opts)


if __name__ == '__main__':
    command()
