#!/usr/bin/env python3

import argparse
import os
import random

import girder_client.cli


def copy_folder(gcs, gcd, sparent, dparent):
    for sfolder in gcs.listFolder(sparent['_id'], sparent['_modelType']):
        print('folder', sfolder['name'])
        dfolder = gcd.createFolder(
            dparent['_id'], sfolder['name'], sfolder['description'],
            dparent['_modelType'], sfolder['public'], True,
            sparent.get('meta', {}))
        copy_folder(gcs, gcd, sfolder, dfolder)
    if sparent['_modelType'] != 'folder':
        return
    for sitem in gcs.listItem(sparent['_id']):
        print('item', gcs.get(f'resource/{sitem["_id"]}/path', parameters={'type': 'item'}))
        ditem = gcd.createItem(
            dparent['_id'], sitem['name'], sitem['description'], True)
        if len(sitem.get('meta', {})):
            gcd.addMetadataToItem(ditem['_id'], sitem.get('meta', {}))
        if len(list(gcs.listFile(sitem['_id']))) != len(list(gcd.listFile(ditem['_id']))):
            for file in gcs.listFile(sitem['_id']):
                print('file', file['name'])
                gcs.downloadFile(file['_id'], 'temp.tmp')
                gcd.uploadFileToItem(
                    ditem['_id'], 'temp.tmp', mimeType=file['mimeType'], filename=file['name'])
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
    stop = gcs.get('resource/lookup', parameters={'path': opts.src_path})
    try:
        dtop = gcd.get('resource/lookup', parameters={'path': opts.dest_path})
    except girder_client.HttpError:
        dtop = None
    if dtop is None and stop['_modelType'] in {'user', 'collection'}:
        dest_parts = opts.dest_path.rstrip(os.path.sep).split(os.path.sep)
        if len(dest_parts) == 3 and dest_parts[0] == '' and (
                dest_parts[1] == 'colelction' or dest_parts[1] == stop['_modelType']):
            if dest_parts[1] == 'user':
                dtop = gcd.createUser(
                    stop['login'], stop['email'], stop['firstName'],
                    stop['lastName'], str(random.random()), stop['admin'])
            elif stop['_modelType'] == 'user':
                dtop = gcd.createCollection(stop['login'], 'From user account', False)
            else:
                dtop = gcd.createCollection(stop['name'], stop['description'], stop['public'])
    copy_folder(gcs, gcd, stop, dtop)


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
    parser.add_argument('--dest-path', help='Destination resource path.')
    opts = parser.parse_args()
    copy_data(opts)
