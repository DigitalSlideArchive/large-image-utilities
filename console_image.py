#!/usr/bin/env python3

import argparse
import os
import sys

import large_image
import numpy as np
import PIL.Image
import PIL.ImageOps


def to_dots(clr, bw, usecolor):
    out = ''
    if usecolor:
        out += f'\033[38;2;{clr[0]};{clr[1]};{clr[2]}m'
    flat = bw.T.flatten()
    val = sum(2**idx if flat[idx] else 0 for idx in range(8))
    out += chr(0x2800 + val)
    return out


def main(opts):
    try:
        termw, termh = os.get_terminal_size()
    except OSError:
        termw, termh = 80, 25
    if opts.width:
        termw = opts.width
    if opts.height:
        termh = opts.height

    width = termw * 2
    height = termh * 4
    aspect_ratio = 0.55 * 2
    color = opts.color

    thumbw = width if aspect_ratio < 1 else int(width * aspect_ratio)
    thumbh = height if aspect_ratio > 1 else int(height / aspect_ratio)

    try:
        img = large_image.open(opts.source).getThumbnail(
            format='PIL', width=thumbw, height=thumbh)[0]
    except Exception:
        return ''
    thumbw, thumbh = img.size

    if aspect_ratio < 1:
        charw, charh = thumbw // 2, int(thumbh * aspect_ratio) // 4
    else:
        charw, charh = int(thumbw / aspect_ratio) // 2, thumbh // 4
    dotw, doth = charw * 2, charh * 4

    adjimg = PIL.ImageOps.autocontrast(img, cutoff=0.02)
    # adjimg = PIL.ImageOps.equalize(img)
    img = PIL.Image.blend(img, adjimg, opts.contrast)

    dotimg = img.resize((dotw, doth)).convert('1', dither=False)
    charimg = img.convert('RGB').resize((charw, charh))

    dots = np.array(dotimg)
    chars = np.array(charimg)

    output = [
        [to_dots(chars[y][x], dots[y * 4:y * 4 + 4, x * 2:x * 2 + 2], color)
         for x in range(chars.shape[1])]
        for y in range(chars.shape[0])
    ]

    output = '\n'.join(''.join(line) for line in output)
    if color:
        output += '\033[39m\033[49m'
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
    opts = parser.parse_args()
    result = main(opts)
    if result:
        print(opts.source)
        sys.stdout.write(result + '\n')


if __name__ == '__main__':
    command()
