#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "girder_client",
#   "pyyaml",
# ]
# ///
# End pep723 blocks

import argparse
import os
import tempfile

import girder_client
import girder_client.cli
import yaml


def get_girder_client(opts):
    """
    Log in to Girder and return a reference to the client.

    :param opts: options that include the username, password, and girder api
        url.
    :returns: the girder client.
    """
    gcopts = {k: v for k, v in opts.items() if k in {
        'username', 'password', 'host', 'port', 'apiRoot', 'scheme', 'apiUrl',
        'apiKey', 'sslVerify'}}
    gcopts['username'] = gcopts.get('username') or None
    gcopts['password'] = gcopts.get('password') or None
    return girder_client.cli.GirderCli(**gcopts)


def format_points(points):
    labeled = {p['label']['value']: [p['center'][0], p['center'][1]]
               for p in points if p.get('label', {}).get('value')}
    if len(labeled):
        return labeled
    unlabeled = [[p['center'][0], p['center'][1]] for p in points]
    return unlabeled


def make_tps_yaml(args, gc):
    folder = gc.get('resource/lookup', parameters={'path': args.folder})
    found = {}
    first = None
    destItem = None
    for item in gc.listItem(folder['_id']):
        if item['name'] == args.dest:
            destItem = item
            continue
        if 'largeImage' in item:
            annots = gc.get('annotation', parameters={
                'itemId': item['_id'], 'name': args.annotation})
            if not annots or not len(annots):
                continue
            annot = gc.get(f'annotation/{annots[0]["_id"]}')
            try:
                points = [p for p in annot['annotation']['elements'] if p['type'] == 'point']
                if not len(points):
                    continue
                found[item['name']] = {'item': item, 'points': points}
                if item['name'] == args.root or (
                        args.root and item['name'] == args.root.split(',')[0]):
                    first = item['_id']
            except Exception:
                pass
    if len(found) < 2:
        print('Insufficient annotated images.')
        return
    order = (args.root or '').split(',')
    found = [found[k[-1]] for k in sorted(
        [(first != found[f]['item']['_id'],
          order.index(found[f]['item']['name'])
          if found[f]['item']['name'] in order else len(order),
          found[f]['item']['name'],
          f) for f in found])]
    sources = [{'path': found[0]['item']['name']}]
    dst = format_points(found[0]['points'])
    for entry in found[1:]:
        sources.append({
            'path': entry['item']['name'],
            'position': {'warp': {'dst': dst, 'src': format_points(entry['points'])}}
        })
    multi = {'backgroundColor': [255, 255, 255], 'sources': sources}
    with tempfile.TemporaryDirectory() as tempDir:
        dest = args.dest or (found[0]['item']['name'].rsplit('.', 1)[0] + '.yaml')
        yamlpath = os.path.join(tempDir, dest)
        with open(yamlpath, 'w') as fptr:
            fptr.write(yaml.dump(multi))
        if not destItem:
            destItem = gc.loadOrCreateItem(dest, folder['_id'], reuseExisting=True)
        gc.delete(f'item/{destItem["_id"]}/tiles')
        for file in gc.listFile(destItem['_id']):
            gc.delete(f'file/{file["_id"]}')
        gc.uploadFileToItem(destItem['_id'], yamlpath)
        gc.addMetadataToItem(destItem['_id'], {
            'composite': (destItem.get('meta').get('composite', 0) or 0) + 1})
        print(f'Uploaded {dest}')


if __name__ == '__main__':  # noqa
    parser = argparse.ArgumentParser(
        description='Read a folder of items.  For those that have an '
        'annotation called Fiducial, use the point annotations to create a '
        'TPS-aligned image multi-source yaml file.  Update an existing item '
        'with the new yaml file.')
    # Standard girder_client CLI options
    parser.add_argument(
        '--apiurl', '--api-url', '--api', '--url', '-a', dest='apiUrl',
        help='The Girder api url (e.g., http://127.0.0.1:8080/api/v1).')
    parser.add_argument(
        '--apikey', '--api-key', '--key', dest='apiKey',
        default=os.environ.get('GIRDER_API_KEY', None),
        help='An API key, defaults to GIRDER_API_KEY environment variable.')
    parser.add_argument(
        '--username', '--user',
        help='The Girder admin username.  If not specified, a prompt is given.')
    parser.add_argument(
        '--password', '--pass', '--passwd', '--pw',
        help='The Girder admin password.  If not specified, a prompt is given.')
    parser.add_argument('--host', help='The Girder API host.')
    parser.add_argument('--scheme', help='The Girder API scheme.')
    parser.add_argument('--port', type=int, help='The Girder API port.')
    parser.add_argument(
        '--apiroot', '--api-root', dest='apiRoot',
        help='The Girder API root.')
    parser.add_argument(
        '--no-ssl-verify', action='store_false', dest='sslVerify',
        help='Disable SSL verification.')
    parser.add_argument(
        '--certificate', dest='sslVerify', help='A path to SSL certificate')
    # Generic verbose option
    parser.add_argument('--verbose', '-v', action='count', default=0)
    # This program's options

    parser.add_argument(
        'folder',
        help='The Girder path to the folder to process')
    parser.add_argument(
        '--annotation', default='Fiducial',
        help='Name of the fiducial annotation')
    parser.add_argument(
        '--root',
        help='If specified, use an image with this name as the base image.  '
        'If not specified, the first C-sort first image is used.  If a comma-'
        'separated list, the images are placed in this order.')
    parser.add_argument(
        '--dest',
        help='If specified, use this as the name of the destination yaml '
        'image.  The default will be the chosen root with the yaml extension.')

    args = parser.parse_args()
    if args.verbose >= 2:
        print('Parsed arguments: %r' % args)
    gc = get_girder_client(vars(args))

    make_tps_yaml(args, gc)
