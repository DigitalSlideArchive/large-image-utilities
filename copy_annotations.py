#!/usr/bin/env python3

import argparse
import json
import os
import random
import tempfile

import girder_client.cli


def copy_folder(gcs, gcd, sparent, dparent, opts):  # noqa
    if (sparent['_modelType'] == 'folder' and dparent['_modelType'] == 'folder' and
            len(sparent.get('meta', {}))):
        # gcd.addMetadataToFolder(dparent['_id'], sparent.get('meta', {}))
        gcd.post(
            f'folder/{dparent["_id"]}/metadata',
            data=json.dumps(sparent['meta']),
            headers={'X-HTTP-Method': 'PUT', 'Content-Type': 'application/json'})
    for sfolder in gcs.listFolder(sparent['_id'], sparent['_modelType']):
        print('folder', sfolder['name'])
        dfolder = gcd.createFolder(
            dparent['_id'], sfolder['name'], sfolder['description'],
            dparent['_modelType'], sfolder['public'], True)
        copy_folder(gcs, gcd, sfolder, dfolder, opts)
    if sparent['_modelType'] != 'folder':
        return
    for sitem in gcs.listItem(sparent['_id']):
        if getattr(opts, 'substr', None) and opts.substr not in sitem['name']:
            continue
        print('item', gcs.get(f'resource/{sitem["_id"]}/path', parameters={'type': 'item'}))
        ditem = gcd.createItem(
            dparent['_id'], sitem['name'], sitem['description'], True)
        if len(sitem.get('meta', {})):
            # gcd.addMetadataToItem(ditem['_id'], sitem.get('meta', {}))
            gcd.post(
                f'item/{ditem["_id"]}/metadata',
                data=json.dumps(sitem['meta']),
                headers={'X-HTTP-Method': 'PUT', 'Content-Type': 'application/json'})
        hasli = 'largeImage' in sitem and 'expected' not in sitem['largeImage']
        setli = None
        if len(list(gcs.listFile(sitem['_id']))) != len(list(gcd.listFile(ditem['_id']))):
            present = list(gcd.listFile(ditem['_id']))
            for file in gcs.listFile(sitem['_id']):
                dfile = None
                for pfile in present:
                    if pfile['name'] == file['name'] and pfile['size'] == file['size']:
                        dfile = pfile
                        break
                if dfile is None:
                    print('file', file['name'], file['size'])
                    with tempfile.TemporaryDirectory() as tmpdirname:
                        temppath = os.path.join(tmpdirname, 'temp.tmp')
                        gcs.downloadFile(file['_id'], temppath)
                        dfile = gcd.uploadFileToItem(
                            ditem['_id'], temppath, mimeType=file['mimeType'],
                            filename=file['name'])
                if hasli and file['_id'] == sitem['largeImage'].get('fileId'):
                    setli = dfile
        if setli:
            ditem = gcd.createItem(
                dparent['_id'], sitem['name'], sitem['description'], True)
            if 'largeImage' not in ditem or ditem['largeImage'].get('fileId') != setli['_id']:
                print('set largeImage fileId')
                gcd.delete(f'item/{ditem["_id"]}/tiles')
                gcd.post(f'item/{ditem["_id"]}/tiles', parameters={'fileId': setli['_id']})
        if opts.replace and len(gcd.get('annotation', parameters={'itemId': ditem['_id']})):
            gcd.delete(f'annotation/item/{ditem["_id"]}')
        if (not len(gcs.get('annotation', parameters={'itemId': sitem['_id']})) or
                len(gcd.get('annotation', parameters={'itemId': ditem['_id']}))):
            continue
        try:
            print('get annotations')
            ann = gcs.get('annotation/item/%s' % sitem['_id'], jsonResp=False).content
        except Exception as e:
            print(e)
            continue
        print('put annotations')
        gcd.post('annotation/item/%s' % ditem['_id'], data=ann)


def copy_data(opts):
    print('Source')
    gcs = girder_client.cli.GirderCli(
        apiUrl=opts.src_api, username=opts.src_user, password=opts.src_password)
    gcs.progressReporterCls = girder_client._NoopProgressReporter
    print('Destination')
    gcd = girder_client.cli.GirderCli(
        apiUrl=opts.dest_api, username=opts.dest_user, password=opts.dest_password)
    gcd.progressReporterCls = girder_client._NoopProgressReporter
    copy_resource(gcs, gcd, opts.src_path, opts.dest_path, opts)


def copy_resource(gcs, gcd, src_path, dest_path, opts):  # noqa
    if dest_path.split(os.path.sep)[-1] == '.':
        dest_path = os.path.sep.join(
            dest_path.split(os.path.sep)[:-1] + src_path.split(os.path.sep)[-1:])
    if src_path == '/':
        for path in ['user', 'collection']:
            copy_resource(
                gcs, gcd, os.path.join(src_path, path), os.path.join(dest_path, path), opts)
    if src_path.rstrip('/') in {'/user', '/collection'}:
        try:
            gcd.get('resource/lookup', parameters={'path': dest_path})
        except Exception:
            dparent = gcd.get('resource/lookup', parameters={'path': os.path.dirname(dest_path)})
            gcd.createFolder(
                dparent['_id'], os.path.basename(dest_path), '',
                dparent['_modelType'], True, True)
    if src_path.rstrip('/') == '/user':
        for user in gcs.listUser():
            user_path = gcs.get(f'resource/{user["_id"]}/path', parameters={'type': 'user'})
            copy_resource(gcs, gcd, user_path, os.path.join(
                dest_path, user_path.split(os.path.sep)[-1]), opts)
    if src_path.rstrip('/') == '/collection':
        for coll in gcs.listCollection():
            coll_path = gcs.get(f'resource/{coll["_id"]}/path', parameters={'type': 'collection'})
            copy_resource(gcs, gcd, coll_path, os.path.join(
                dest_path, coll_path.split(os.path.sep)[-1]), opts)
    stop = gcs.get('resource/lookup', parameters={'path': src_path})
    try:
        dtop = gcd.get('resource/lookup', parameters={'path': dest_path})
    except girder_client.HttpError:
        dtop = None
    if dtop is None and stop['_modelType'] in {'user', 'collection', 'folder'}:
        dest_parts = dest_path.rstrip(os.path.sep).split(os.path.sep)
        try:
            dparent = gcd.get('resource/lookup', parameters={'path': os.path.dirname(dest_path)})
            dtop = gcd.createFolder(
                dparent['_id'], os.path.basename(dest_path), '',
                dparent['_modelType'], True, True)
        except Exception:
            dparent = None
        if dparent is None and len(dest_parts) >= 3 and dest_parts[0] == '' and (
                dest_parts[1] == 'collection' or dest_parts[1] == stop['_modelType']):
            dtop = gcd.get('resource/lookup',
                           parameters={'path': os.path.sep.join(dest_parts[:3])})
            if not dtop:
                if dest_parts[1] == 'user':
                    dtop = gcd.createUser(
                        stop['login'], stop['email'], stop['firstName'],
                        stop['lastName'], str(random.random()), stop['admin'])
                elif stop['_modelType'] == 'user':
                    dtop = gcd.createCollection(stop['login'], 'From user account', False)
                else:
                    dtop = gcd.createCollection(stop['name'], stop['description'], stop['public'])
            for part in dest_parts[3:]:
                dparent = dtop
                dtop = gcd.createFolder(
                    dparent['_id'], part, '',
                    dparent['_modelType'], True, True)
    copy_folder(gcs, gcd, stop, dtop, opts)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Copy folders, items, and annotations from one girder '
        'server to another.')
    parser.add_argument('--src-api', help='Source API url (through /api/v1).')
    parser.add_argument('--dest-api', help='Destination API url (through /api/v1).')
    parser.add_argument('--src-user', help='Source username.')
    parser.add_argument('--dest-user', help='Destination username.')
    parser.add_argument('--src-password', help='Source password.')
    parser.add_argument('--dest-password', help='Destination password.')
    parser.add_argument('--src-path', help='Source resource path.')
    parser.add_argument('--replace', action='store_true', help='Replace all annotations.')
    parser.add_argument('--substr', help='All items must contain this substring.')
    parser.add_argument(
        '--dest-path', help='Destination resource path.  If the last '
        'component of this is ".", it is taken from the last component of '
        'the source resource path.')
    opts = parser.parse_args()
    copy_data(opts)
