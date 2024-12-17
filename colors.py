import argparse
import math
import os
import pprint
import sys

import large_image
import numpy as np
import PIL.Image
import PIL.ImageCms

labtorgb = None
rgbtolab = None


def augment_lab(pal, n, white=True):
    while pal.shape[0] < n:
        if pal.shape[0]:
            lab = palette_to_lab(pal)
        else:
            lab = np.zeros((0, 3), dtype=np.uint8)
        best = None, None, None, None
        for lum in ((255, 192) if white else (0, 63)):
            steps = 1000
            for abdist in [40, 60, 80]:
                for step in range(steps):
                    ang = math.pi * 2 * step / steps
                    a = round(127.5 + abdist * math.cos(ang))
                    b = round(127.5 + abdist * math.sin(ang))
                    rgb = lab_to_palette(np.array([[lum, a, b]]))
                    ll, aa, bb = palette_to_lab(rgb).tolist()[0]
                    sdist = None
                    for idx in range(lab.shape[0]):
                        dist = (((float(lab[idx][0]) - ll) * 100 / 255) ** 2 +
                                (float(lab[idx][1]) - aa) ** 2 +
                                (float(lab[idx][2]) - bb) ** 2)
                        if sdist is None or dist < sdist:
                            sdist = dist
                    if sdist is None or best[0] is None or sdist > best[0]:
                        best = sdist, rgb
                    if best[0] is None:
                        break
                if best[0] is None:
                    break
            if best[0] is None:
                break
        pal = np.array(pal.tolist() + best[1].tolist())
    return pal


def augment_hsv(pal, n, white=True):
    while pal.shape[0] < n:
        if pal.shape[0]:
            hsv = palette_to_hsv(pal)
        else:
            hsv = np.zeros((0, 3), dtype=np.uint8)
        best = None, None, None, None
        for lum in ((255, 192) if white else (0, 63)):
            for sat in (255, 192):
                for hue in range(255):
                    rgb = hsv_to_palette(np.array([[hue, sat, lum]]))
                    sdist = None
                    for idx in range(hsv.shape[0]):
                        dist = ((float(hsv[idx][0]) - hue) ** 2 +
                                (float(hsv[idx][1]) - sat) ** 2 +
                                (float(hsv[idx][2]) - lum) ** 2)
                        if sdist is None or dist < sdist:
                            sdist = dist
                    if sdist is None or best[0] is None or sdist > best[0]:
                        best = sdist, rgb
                    if best[0] is None:
                        break
                if best[0] is None:
                    break
        pal = np.array(pal.tolist() + best[1].tolist())
    return pal


def show_palette(pal):
    try:
        termw, termh = os.get_terminal_size()
    except OSError:
        termw = 80
    out = []
    width = max(1, termw // pal.shape[0])
    for clr in pal.tolist():
        out.append(f'\033[48;2;{clr[0]};{clr[1]};{clr[2]}m' + ' ' * width)
    out.append('\033[49m')
    if len(pal.tolist()) > termw:
        left = termw - (len(pal.tolist()) - (len(pal.tolist()) // termw) * termw)
        if left and left != termw:
            out.append(' ' * left)
    print(''.join(out))


def palette_to_hsv(pal):
    image = PIL.Image.fromarray(pal[None, ...].astype(np.uint8), 'RGBA')
    hsvimg = image.convert('HSV')
    return np.asarray(hsvimg)[0, :, :]


def hsv_to_palette(hsvarr):
    image = PIL.Image.fromarray(hsvarr[None, ...].astype(np.uint8), 'HSV')
    rgbimg = image.convert('RGBA')
    return np.asarray(rgbimg)[0, :, :]


def sort_by_hue(pal):
    hsvarr = palette_to_hsv(pal).tolist()
    ordered = sorted([(val, idx) for idx, val in enumerate(hsvarr)])
    hsvpal = np.array([pal[idx, :] for val, idx in ordered])
    return hsvpal


def palette_to_lab(pal):
    global rgbtolab

    image = PIL.Image.fromarray(pal[None, ...].astype(np.uint8), 'RGBA')
    if not rgbtolab:
        srgb = PIL.ImageCms.createProfile('sRGB')
        lab = PIL.ImageCms.createProfile('LAB')
        rgbtolab = PIL.ImageCms.buildTransformFromOpenProfiles(srgb, lab, 'RGB', 'LAB')
    labimg = PIL.ImageCms.applyTransform(image.convert('RGB'), rgbtolab)
    return np.asarray(labimg)[0, :, :]


def lab_to_palette(labarr):
    global labtorgb

    image = PIL.Image.fromarray(labarr[None, ...].astype(np.uint8), 'LAB')
    if not labtorgb:
        srgb = PIL.ImageCms.createProfile('sRGB')
        lab = PIL.ImageCms.createProfile('LAB')
        labtorgb = PIL.ImageCms.buildTransformFromOpenProfiles(lab, srgb, 'LAB', 'RGB')
    rgbimg = PIL.ImageCms.applyTransform(image, labtorgb).convert('RGBA')
    return np.asarray(rgbimg)[0, :, :]


def sort_by_lab(pal):
    labarr = palette_to_lab(pal).tolist()
    ordered = sorted([(val, idx) for idx, val in enumerate(labarr)])
    labpal = np.array([pal[idx, :] for val, idx in ordered])
    return labpal


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Generate a set of perceptually separate colors.')
    parser.add_argument(
        '--number', '-n', type=int, help='The number of colors to generate.')
    parser.add_argument(
        '--scheme', default='lab', help='The scheme to use to separate the '
        'colors; this can be "lab" or "hsv".')
    parser.add_argument(
        '--palette', help='A starting palette.  One of '
        'large_image.tilesource.utilities.getAvailableNamedPalettes().  '
        '"list" to list known palettes.')
    parser.add_argument(
        '--white', action='store_true', default=True,
        help='Optimize for a white background.')
    parser.add_argument(
        '--black', action='store_false', dest='white',
        help='Optimize for a black background.')
    opts = parser.parse_args()
    base = np.zeros((0, 4), dtype=float)
    if opts.palette in ('list', '--list'):
        pprint.pprint(large_image.tilesource.utilities.getAvailableNamedPalettes())
        sys.exit(0)
    if opts.palette:
        base = large_image.tilesource.utilities.getPaletteColors(opts.palette)
    if opts.number and len(base) > opts.number:
        base = base[:opts.number]
    if opts.number and opts.number > len(base):
        if opts.scheme == 'lab':
            base = augment_lab(base, opts.number, opts.white)
        elif opts.scheme == 'hsv':
            base = augment_hsv(base, opts.number)
    pal = []
    for clr in base.tolist():
        pal.append((f'#{clr[0]:02x}{clr[1]:02x}{clr[2]:02x}{clr[3]:02x}')[
            :9 if clr[3] != 255 else 7])
    print('palette, in order, by hue, by L*a*b')
    print(pal)
    show_palette(base)
    show_palette(sort_by_hue(base))
    show_palette(sort_by_lab(base))
