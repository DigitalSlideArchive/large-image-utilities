#!/usr/bin/env python3

# pip install girder_client

import argparse
import hashlib
import json
import os
import subprocess
import time

import girder_client
import girder_client.cli


def generate_hash(gc, opts, file):
    if file.get('sha512') or file.get('linkUrl'):
        return 0
    path = gc.get(f'resource/{file["_id"]}/path', parameters={'type': 'file'})
    if opts.verbose >= 2:
        print(f'Getting hash for {path}')
    try:
        gc.post(f'file/{file["_id"]}/hashsum')
    except Exception:
        if opts.verbose >= 1:
            print(f'--> Cannot get hash of {path} ({file})')
        return 0
    return 1


def walk_files(gc, opts, baseFolder=None, query=None):  # noqa
    if query and baseFolder is None and not getattr(opts, 'filter', None):
        q = {'itemId': {'$exists': True}, 'linkUrl': {'$exists': False},
             'attachedToId': {'$exists': False}}
        q.update(query)
        params = {'query': json.dumps(q), 'sort': '_id', 'sortdir': -1 if opts.reverse else 1}
        try:
            yield from gc.listResource('file/query', params=params)
            return
        except Exception:
            pass
    if baseFolder is None:
        if not opts.reverse:
            for user in gc.listUser():
                if getattr(opts, 'filter', None) and user['login'] != opts.filter:
                    continue
                for folder in gc.listFolder(user['_id'], 'user'):
                    for file in walk_files(gc, opts, folder):
                        yield file
            for coll in gc.listCollection():
                if getattr(opts, 'filter', None) and coll['name'] != opts.filter:
                    continue
                for folder in gc.listFolder(coll['_id'], 'collection'):
                    for file in walk_files(gc, opts, folder):
                        yield file
        else:
            for coll in list(gc.listCollection())[::-1]:
                if getattr(opts, 'filter', None) and coll['name'] != opts.filter:
                    continue
                for folder in list(gc.listFolder(coll['_id'], 'collection'))[::-1]:
                    for file in walk_files(gc, opts, folder):
                        yield file
            for user in list(gc.listUser())[::-1]:
                if getattr(opts, 'filter', None) and user['login'] != opts.filter:
                    continue
                for folder in list(gc.listFolder(user['_id'], 'user'))[::-1]:
                    for file in walk_files(gc, opts, folder):
                        yield file
        return
    if not opts.reverse:
        for folder in gc.listFolder(baseFolder['_id'], 'folder'):
            for file in walk_files(gc, opts, folder):
                yield file
        for item in gc.listItem(baseFolder['_id']):
            for file in gc.listFile(item['_id']):
                yield file
    else:
        for folder in list(gc.listFolder(baseFolder['_id'], 'folder'))[::-1]:
            for file in walk_files(gc, opts, folder):
                yield file
        for item in list(gc.listItem(baseFolder['_id']))[::-1]:
            for file in gc.listFile(item['_id']):
                yield file


def scan_mount(base, known, opts, exclude=False):
    start = time.time()
    last = start
    for line in subprocess.Popen(['find', base, '-type', 'f'],
                                 stdout=subprocess.PIPE).stdout:
        path = os.path.join(base, line[:-1].decode())
        flen = os.path.getsize(path)
        if exclude:
            if flen not in known['len'] or path not in known['len'][flen]:
                continue
            known['len'][flen].pop(path)
            if not len(known['len'][flen]):
                known['len'].pop(flen)
        else:
            # Use dictionaries, not sets, so that they are ordered
            known['len'].setdefault(flen, {})
            known['len'][flen][path] = True
        if time.time() - last > 10 and opts.verbose >= 2:
            print('  %3.5fs - %d distinct lengths, %d files' % (
                time.time() - start, len(known['len']),
                sum(len(x) for x in known['len'].values())))
            last = time.time()
    """
    for root, _dirs, files in os.walk(base):
        for file in files:
            path = os.path.join(base, root, file)
            flen = os.path.getsize(path)
            known['len'].setdefault(flen, set())
            known['len'][flen].add(path)
            if time.time() - last > 10 and opts.verbose >= 2:
                print('  %3.5fs - %d distinct lengths, %d files' % (
                    time.time() - start, len(known['len']),
                    sum(len(x) for x in known['len'].values())))
                last = time.time()
    """
    if opts.verbose >= 2:
        print('  %3.5fs - %d distinct lengths, %d files' % (
            time.time() - start, len(known['len']),
            sum(len(x) for x in known['len'].values())))


def get_fsassetstore(gc):
    for assetstore in gc.listResource('assetstore'):
        if assetstore.get('type') == 0:
            return assetstore
    raise Exception('No fs assetstore')


def match_sha(file, known, opts):
    if file['sha512'] in known['sha']:
        return known['sha'][file['sha512']]
    if file['size'] not in known['len']:
        return
    for path in known['len'][file['size']]:
        if path not in known['path']:
            if opts.verbose >= 3:
                print('    Getting sha for %s' % path)
            sha = hashlib.sha512()
            with open(path, 'rb') as f:
                while True:
                    data = f.read(65536)
                    if not data:
                        break
                    sha.update(data)
            sha = sha.hexdigest()
            known['path'][path] = sha
            known['sha'][sha] = path
            if file['sha512'] == sha:
                return path


def adjust_to_import(gc, opts, assetstore, known, file):
    if not file.get('sha512'):
        return
    if not file['size']:
        return
    file = gc.get(f'resource/{file["_id"]}', parameters={'type': 'file'})
    if not file.get('imported') and file['size'] >= opts.size:
        path = match_sha(file, known, opts)
        if not path:
            return
        if opts.verbose >= 1:
            print('Move %s (%s) to %s' % (file['name'], file['_id'], path))
        gc.post(f'file/{file["_id"]}/import/adjust_path', parameters={'path': path})
    elif file.get('imported') and 'path' in file and file.get('size'):
        if file['size'] in known['len'] and list(known['len'][file['size']])[0] == file['path']:
            return
        path = match_sha(file, known, opts)
        if not path or file['path'] == path:
            return
        if opts.verbose >= 1:
            print('Move %s (%s) to %s' % (file['name'], file['_id'], path))
        gc.post(f'file/{file["_id"]}/import/adjust_path', parameters={'path': path})


def adjust_current_import(gc, opts, assetstore, known, file):
    if not file.get('sha512'):
        return
    if not file['size']:
        return
    file = gc.get(f'resource/{file["_id"]}', parameters={'type': 'file'})
    if file.get('imported'):
        try:
            next(gc.downloadFileAsIterator(file['_id']))
            return
        except Exception:
            pass
        path = match_sha(file, known, opts)
        if not path:
            path = gc.get(f'resource/{file["_id"]}/path', parameters={'type': 'file'})
            if opts.verbose >= 1:
                print(f'--> File is missing: {path}')
            return
        if opts.verbose >= 1:
            print('Adjust %s (%s) to %s' % (file['name'], file['_id'], path))
        gc.post(f'file/{file["_id"]}/import/adjust_path', parameters={'path': path})


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


def check_assetstore(gc, opts):
    basepath = os.path.realpath(os.path.expanduser(opts.assetstore))
    start = time.time()
    last = start
    checked = 0
    removed = 0
    for line in subprocess.Popen(['find', basepath, '-type', 'f'],
                                 stdout=subprocess.PIPE).stdout:
        path = line.decode().rstrip()
        if not path.startswith(basepath):
            continue
        subpath = path[len(basepath):].lstrip(os.path.sep)
        if not os.path.isfile(os.path.join(basepath, subpath)):
            continue
        first = subpath.split(os.path.sep)[0]
        try:
            if first != 'temp' and int(first, 16) >= 256:
                continue
        except ValueError:
            continue
        if time.time() - last > 10 and opts.verbose >= 2:
            print('  %3.5fs - %d files checked, %d removed' % (
                time.time() - start, checked, removed))
            last = time.time()
        q = {'imported': {'$exists': False}, 'path': subpath}
        params = {'query': json.dumps(q)}
        result = list(gc.listResource('file/query', params=params, limit=1))
        checked += 1
        if len(result):
            continue
        os.unlink(os.path.join(basepath, subpath))
        removed += 1
        if opts.verbose >= 1:
            print('Removed abandoned file %s' % subpath)
    if opts.verbose >= 2:
        print('  %3.5fs - %d files checked, %d removed' % (
            time.time() - start, checked, removed))


if __name__ == '__main__':  # noqa
    parser = argparse.ArgumentParser(
        description='Adjust import paths.')
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
        '--mount', action='append',
        help='Mounted directories that a file system assetstore should use '
        'for adjustment.')
    parser.add_argument(
        '--exclude', action='append',
        help='Mounted directories to exclude from cataloged data used in '
        'adjustment.  All excludes are processed after all mounts.')
    parser.add_argument(
        '--size', type=int, default=100000,
        help='Minimum size of a file to remove from uploads and move to imports')
    parser.add_argument(
        '--hash', default=True, action='store_true',
        help='Make sure all files have computed hash values (default).')
    parser.add_argument('--no-hash', dest='hash', action='store_false')
    parser.add_argument(
        '--direct', default=True, action='store_true',
        help='Check if direct (non-imported) files could be moved to '
        'reference imported paths (default).')
    parser.add_argument('--no-direct', dest='direct', action='store_false')
    parser.add_argument(
        '--valid', default=True, action='store_true',
        help='Check if import paths are still valid or have moved (default).')
    parser.add_argument('--no-valid', dest='valid', action='store_false')
    parser.add_argument(
        '--earlier', default=True, action='store_true',
        help='Make imported file references point to the first listed such '
        'reference (default).')
    parser.add_argument('--no-earlier', dest='earlier', action='store_false')
    parser.add_argument('--reverse', action='store_true')
    parser.add_argument(
        '--filter', help='Only process users and collections that match this string')
    parser.add_argument(
        '--assetstore', help='Directory of the assetstore to check for abandoned files.')

    opts = parser.parse_args()
    if opts.verbose >= 2:
        print('Parsed arguments: %r' % opts)
    gc = get_girder_client(vars(opts))
    lastlog = time.time()
    count = 0
    hashcount = 0
    if opts.hash:
        for file in walk_files(gc, opts, query={'sha512': {'$exists': False}}):
            hashcount += generate_hash(gc, opts, file)
            count += 1
            if time.time() - lastlog > 10 and opts.verbose >= 2:
                print('Hashed %d/%d files' % (hashcount, count))
                lastlog = time.time()
        if opts.verbose >= 2:
            print('Hashed %d/%d files' % (hashcount, count))
    known_files = {'len': {}, 'sha': {}, 'path': {}}
    if opts.direct or opts.valid or opts.earlier:
        for mount in opts.mount:
            if opts.verbose >= 2:
                print('Scanning %s' % mount)
            scan_mount(mount, known_files, opts)
        for mount in opts.exclude:
            if opts.verbose >= 2:
                print('Scanning %s for exclusion' % mount)
            scan_mount(mount, known_files, opts, True)
    assetstore = get_fsassetstore(gc)
    if opts.direct:
        count = 0
        for file in walk_files(gc, opts, query={
                'sha512': {'$exists': True}, 'imported': {'$exists': False},
                'size': {'$exists': True, '$gte': opts.size}}):
            adjust_to_import(gc, opts, assetstore, known_files, file)
            count += 1
            if time.time() - lastlog > 10 and opts.verbose >= 2:
                print('Checked direct %d/%d files' % (len(known_files['path']), count))
                lastlog = time.time()
        if opts.verbose >= 2:
            print('Checked direct %d/%d files' % (len(known_files['path']), count))
    if opts.earlier:
        count = 0
        for file in walk_files(gc, opts, query={
                'sha512': {'$exists': True}, 'imported': {'$exists': True},
                'size': {'$exists': True}, 'path': {'$exists': True}}):
            adjust_to_import(gc, opts, assetstore, known_files, file)
            count += 1
            if time.time() - lastlog > 10 and opts.verbose >= 2:
                print('Checked earlier %d/%d files' % (len(known_files['path']), count))
                lastlog = time.time()
        if opts.verbose >= 2:
            print('Checked earlier %d/%d files' % (len(known_files['path']), count))
    if opts.valid:
        count = 0
        for file in walk_files(gc, opts, query={
                'sha512': {'$exists': True}, 'imported': True,
                'size': {'$exists': True}}):
            adjust_current_import(gc, opts, assetstore, known_files, file)
            count += 1
            if time.time() - lastlog > 10 and opts.verbose >= 2:
                print('Checked import %d/%d files' % (len(known_files['path']), count))
                lastlog = time.time()
        if opts.verbose >= 2:
            print('Checked import %d/%d files' % (len(known_files['path']), count))
    if opts.assetstore:
        check_assetstore(gc, opts)
