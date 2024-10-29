#!/usr/bin/env python3

# pip install girder_client

import argparse
import json
import os

import girder_client
import girder_client.cli


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
    gcopts['retries'] = 5
    return girder_client.cli.GirderCli(**gcopts)


if __name__ == '__main__':  # noqa
    parser = argparse.ArgumentParser(
        description='Show top non-imported files by size per assetstore.')
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
        '--count', '-n', type=int, default=10, help='How many files to show '
        'per assetstore')

    opts = parser.parse_args()
    if opts.verbose >= 2:
        print('Parsed arguments: %r' % opts)
    gc = get_girder_client(vars(opts))
    assetstores = gc.listResource('assetstore')
    assetstores = sorted(assetstores, key=lambda a: (a['name'], a['_id']))
    for assetstore in assetstores:
        any = False
        for file in gc.listResource('file/query', params={'query': json.dumps({
            'assetstoreId': {'$oid': assetstore['_id']},
            'imported': {'$exists': False},
            's3Key': {'$exists': False},
            'size': {'$ne': 0},
        }), 'sort': 'size', 'sortdir': -1}, limit=opts.count):
            try:
                path = gc.get(f'resource/{file["_id"]}/path', parameters={'type': 'file'})
            except Exception:
                path = f'No path to {file["name"]}: {file["_id"]}'
                file = gc.get(f'resource/{file["_id"]}', parameters={'type': 'file'})
                if file.get('attachedToType') and file.get('attachedToId'):
                    try:
                        atpath = gc.get(f'resource/{file["attachedToId"]}/path',
                                        parameters={'type': file['attachedToType']})
                        path += f' attached to {atpath}'
                    except Exception:
                        pass
            if not any:
                print(assetstore['name'])
                any = True
            print(f'{file["size"]:12d} {path}')
