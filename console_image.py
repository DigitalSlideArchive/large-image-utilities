#!/usr/bin/env python3

import argparse
import ctypes
import os
import sys

import large_image
import numpy as np
import PIL.Image
import PIL.ImageOps


def to_dots(bw):
    flat = bw.T.flatten()
    val = sum(2**idx if flat[idx] else 0 for idx in range(8))
    return chr(0x2800 + val)


def to_blocks(blocks, usecolor, x, vblocks):
    fac = [0.3, 0.59, 0.11]
    hdist = sum((float(blocks[1][0][idx]) - blocks[0][0][idx]) ** 2 * fac[idx]
                for idx in range(3))
    vdist = sum((float(vblocks[0][1][idx]) - vblocks[0][0][idx]) ** 2 * fac[idx]
                for idx in range(3))
    # The factor after vdist makes it more pleasing even though technically
    # lower in color resolution
    if hdist <= vdist * 4:
        out = (f'\033[48;2;{blocks[0][0][0]};{blocks[0][0][1]};{blocks[0][0][2]}m'
               f'\033[38;2;{blocks[1][0][0]};{blocks[1][0][1]};{blocks[1][0][2]}m' +
               '\u2584')
    else:
        out = (f'\033[48;2;{vblocks[0][0][0]};{vblocks[0][0][1]};{vblocks[0][0][2]}m'
               f'\033[38;2;{vblocks[0][1][0]};{vblocks[0][1][1]};{vblocks[0][1][2]}m' +
               '\u2590')
    if usecolor is not None:
        if usecolor.get('last', None) == out and x and usecolor['last'][-1:] == '\u2584':
            out = usecolor['last'][-1:]
        else:
            usecolor['last'] = out
    return out


def main(opts):
    try:
        termw, termh = os.get_terminal_size()
        termh -= 2
    except OSError:
        termw, termh = 80, 25
    if opts.width:
        termw = opts.width
    if opts.height:
        termh = opts.height

    width = termw * 2
    height = termh * 4
    # aspect_ratio = 0.55 * 2
    aspect_ratio = 0.5 * 2
    color = opts.color

    thumbw = width if aspect_ratio < 1 else int(width * aspect_ratio)
    thumbh = height if aspect_ratio > 1 else int(height / aspect_ratio)

    try:
        if not opts.use:
            ts = large_image.open(opts.source)
        else:
            large_image.tilesource.loadTileSources()
            ts = large_image.tilesource.AvailableTileSources[opts.use](opts.source)
    except Exception:
        return ''
    img = ts.getThumbnail(format='PIL', width=thumbw, height=thumbh)[0]
    thumbw, thumbh = img.size

    if aspect_ratio < 1:
        charw, charh = thumbw // 2, int(thumbh * aspect_ratio) // 4
    else:
        charw, charh = int(thumbw / aspect_ratio) // 2, thumbh // 4
    dotw, doth = charw, charh * 2
    if not opts.color:
        dotw, doth = dotw * 2, doth * 2

    adjimg = PIL.ImageOps.autocontrast(img, cutoff=0.02)
    # adjimg = PIL.ImageOps.equalize(img)
    img = PIL.Image.blend(img, adjimg, opts.contrast)

    if opts.color:
        blockimg = np.array(img.convert('RGB').resize((dotw, doth)))
        vblockimg = np.array(img.convert('RGB').resize((dotw * 2, doth // 2)))

        lastcolor = {} if color else None

        output = [
            [to_blocks(blockimg[y:y + 2, x:x + 1], lastcolor, x,
                       vblockimg[y // 2: y // 2 + 1, x * 2: x * 2 + 2])
             for x in range(blockimg.shape[1])]
            for y in range(0, blockimg.shape[0], 2)
        ]
        output = '\033[39m\033[49m\n'.join(''.join(line) for line in output)
        output += '\033[39m\033[49m'
    else:
        blockimg = img.convert('RGB').resize((dotw, doth))
        palimg = np.array(blockimg.convert('P').quantize(
            colors=2, method=PIL.Image.Quantize.MEDIANCUT,
            dither=PIL.Image.Dither.FLOYDSTEINBERG))
        output = [
            [to_dots(1 - palimg[y:y + 4, x:x + 2])
             for x in range(0, palimg.shape[1], 2)]
            for y in range(0, palimg.shape[0], 4)
        ]
        output = '\n'.join(''.join(line) for line in output)
    return output


def command():
    parser = argparse.ArgumentParser(
        description='Render a large image to the console.')
    parser.add_argument(
        'source', help='Source file to display')
    parser.add_argument(
        '--width', '-w', type=int,
        help='Width of the output; defaults to terminal width.')
    parser.add_argument(
        '--height', type=int,
        help='height of the output; defaults to terminal width.')
    parser.add_argument(
        '--color', '-c', action='store_true', default=True,
        help='Display in color.')
    parser.add_argument(
        '--no-color', '-n', action='store_false', dest='color',
        help='Do not send color escape codes.')
    parser.add_argument(
        '--contrast', type=float, default=0.25,
        help='Increase the contrast.  0 is no change, 1 is full.')
    parser.add_argument(
        '--use', help='Use a specific tile source.')
    opts = parser.parse_args()
    result = main(opts)
    if result:
        try:
            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
        except Exception:
            pass
        print(opts.source)
        sys.stdout.write(result + '\n')


if __name__ == '__main__':
    command()
