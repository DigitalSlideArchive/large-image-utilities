#!/usr/bin/env python3

import argparse

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
        print('item', sitem['name'])
        ditem = gcd.createItem(
            dparent['_id'], sitem['name'], sitem['description'], True, sitem.get('meta', {}))
        if len(list(gcs.listFile(sitem['_id']))) != len(list(gcd.listFile(ditem['_id']))):
            for file in gcs.listFile(sitem['_id']):
                print('file', file['name'])
                gcs.downloadFile(file['_id'], 'temp.tmp')
                gcd.uploadFileToItem(
                    ditem['_id'], 'temp.tmp', mimeType=file['mimeType'], filename=file['name'])
        if (not len(gcs.get('/annotation', parameters={'itemId': sitem['_id']})) or
                len(gcd.get('/annotation', parameters={'itemId': ditem['_id']}))):
            continue
        try:
            print('annotations')
            ann = gcs.get('/annotation/item/%s' % sitem['_id'], jsonResp=False).content
        except Exception as e:
            print(e)
            continue
        print('annotations up')
        gcd.post('/annotation/item/%s' % ditem['_id'], data=ann)


def copy_data(opts):
    print('Source')
    gcs = girder_client.cli.GirderCli(
        apiUrl=opts.src_api, username=opts.src_user, password=opts.src_password)
    gcs.progressReporterCls = girder_client._NoopProgressReporter
    print('Destination')
    gcd = girder_client.cli.GirderCli(
        apiUrl=opts.dest_api, username=opts.dest_user, password=opts.dest_password)
    gcd.progressReporterCls = girder_client._NoopProgressReporter
    stop = gcs.get('/resource/lookup', parameters={'path': opts.src_path})
    dtop = gcd.get('/resource/lookup', parameters={'path': opts.dest_path})
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
