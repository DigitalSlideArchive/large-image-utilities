#!/usr/bin/env python3

import argparse
import pprint

import SimpleITK


def scan_simpleitk(source):
    try:
        img = SimpleITK.ReadImage(source)
    except Exception:
        print('Cannot read')
        return
    metadata = {k: img.GetMetaData(k) for k in img.GetMetaDataKeys()}
    propNames = {
        'GetDepth': 'depth',
        'GetDimension': 'dimension',
        'GetHeight': 'height',
        'GetNumberOfComponentsPerPixel': 'components_per_pixel',
        'GetPixelID': 'pixel_id_type',
        'GetPixelIDTypeAsString': 'pixel_id_type_string',
        'GetPixelIDValue': 'pixel_id_value',
        'GetSize': 'size',
        'GetSizeOfPixelComponent': 'size_of_component',
        'GetWidth': 'width',
        'GetOrigin': 'origin',
        'GetSpacing': 'spacing',
        'GetDirection': 'direction',
    }
    props = {v: getattr(img, k)() for k, v in propNames.items()}
    pprint.pprint({'metadata': metadata, 'image': props})


def command():
    parser = argparse.ArgumentParser(
        description='Scan a file that can be read by SimpleITK and report on '
        'it.')
    parser.add_argument(
        'source', type=str, help='Source file to read and analyze.')
    opts = parser.parse_args()
    print(opts.source)
    scan_simpleitk(opts.source)


if __name__ == '__main__':
    command()
