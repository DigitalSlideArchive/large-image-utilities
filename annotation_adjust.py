import argparse
import json
import os
import tempfile

import girder_client
import girder_client.cli
import large_image


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



if __name__ == '__main__':  # noqa
    parser = argparse.ArgumentParser(
        description='Adjust annotation coordinates for scn files that had '
        'opened with openslide and now open with tifffile.')
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
        '--apiroot', '--api-root', '--root', dest='apiRoot',
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
        '--folder', '--id', dest='folder',
        help='The Girder folder id to process')

    args = parser.parse_args()
    if args.verbose >= 2:
        print('Parsed arguments: %r' % args)
    gc = get_girder_client(vars(args))
    for item in gc.listResource('item', {'folderId': args.folder, 'sort': 'updated'}):
        print(item['name'])
        limeta = oldmeta = None
        for file in gc.listFile(item['_id']):
            if file['_id'] == item['largeImage'].get('fileId'):
                with tempfile.TemporaryDirectory() as tmpdirname:
                    temppath = os.path.join(tmpdirname, file['name'])
                    gc.downloadFile(file['_id'], temppath)
                    ts = large_image.open(temppath)
                    limeta = ts.metadata
                    view = ts._xml['scn']['collection']['image'][-1]['view']
        if not limeta or limeta == oldmeta:
            continue
        dx = float(view['offsetX']) * limeta['sizeX'] / float(view['sizeX'])
        dy = float(view['offsetY']) * limeta['sizeY'] / float(view['sizeY'])
        print(limeta['sizeX'], limeta['sizeY'], dx, dy)
        if not dx and not dy:
            continue
        annList = gc.get('annotation/item/%s' % item['_id'], jsonResp=False).json()
        for ann in annList:
            elements = ann.get('annotation', ann).get('elements')
            # for element in elements:
            for element in elements:
                for pt in element['points']:
                    pt[0] -= dx
                    pt[1] -= dy
            print(len(elements))
        gc.delete(f'annotation/item/{item["_id"]}')
        gc.post('annotation/item/%s' % item['_id'], data=json.dumps(annList))
