#!/usr/bin/env python3
import argparse
import json
import os
import tarfile
import tempfile
from pathlib import Path


def truncate_image(src, keep_layers, dest, dry_run=False):
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        print(f'Extracting {src}...')
        with tarfile.open(src) as tar:
            tar.extractall(path=tmpdir)
        manifest_path = tmpdir / 'manifest.json'
        with open(manifest_path) as f:
            manifest = json.load(f)
        full_layers = manifest[0]['Layers']
        config_path = tmpdir / manifest[0]['Config']
        with open(config_path) as f:
            config = json.load(f)
        history = config.get('history', [])
        diff_ids = config['rootfs'].get('diff_ids', [])
        new_history = []
        new_diff_ids = []
        new_layers = []
        diff_idx = 0
        layer_idx = 0
        for h in history:
            if len(new_history) >= keep_layers:
                break
            desc = h['created_by'].split(None, 1)[1].split(' -c ', 1)[-1]
            desc = ' '.join(desc.split())
            print(f'{len(new_history) + 1:3d}: {desc[:74]}')
            new_history.append(h)
            if not h.get('empty_layer', False):
                if diff_idx < len(diff_ids):
                    new_diff_ids.append(diff_ids[diff_idx])
                    diff_idx += 1
                if layer_idx < len(full_layers):
                    new_layers.append(full_layers[layer_idx])
                    layer_idx += 1
        config['history'] = new_history
        config['rootfs']['diff_ids'] = new_diff_ids

        manifest[0]['Layers'] = new_layers
        with open(manifest_path, 'w') as f:
            json.dump(manifest, f, indent=2)
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)

        for diff_id in set(diff_ids) - set(new_diff_ids):
            diff_id = diff_id.split(':', 1)[-1]
            # print(f'rm {diff_id}')
            os.unlink(tmpdir / 'blobs' / 'sha256' / diff_id)
        if not dry_run:
            print(f'Creating output: {dest}')
            with tarfile.open(dest, 'w') as out_tar:
                for item in os.listdir(tmpdir):
                    out_tar.add(os.path.join(tmpdir, item), arcname=item)
        print(f'Image truncated to first {len(new_history)} layers.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Truncate Docker image to first N layers, including metadata layers.',
    )
    parser.add_argument('src', help='Path to input Docker image tarball')
    parser.add_argument('dest', help='Path to output truncated tarball')
    parser.add_argument(
        '--keep', type=int, help='Number of layers to keep')
    parser.add_argument(
        '--dry-run', '-n', action='store_true',
        help='Report without creating the output')

    args = parser.parse_args()

    truncate_image(args.src, args.keep, args.dest, args.dry_run)
