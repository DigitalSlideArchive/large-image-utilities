#!/usr/bin/env python3

import argparse
import functools
import hashlib
import json
import logging
import os
import re
import shutil
import sys
import tempfile
import time
import zipfile

import girder_client.cli
import requests
import yaml

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


class IndentDumper(yaml.Dumper):

    def increase_indent(self, flow=False, indentless=False):
        """
        Indent lists to make them more aesthetically pleasing.
        """
        return super().increase_indent(flow, False)


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
    gc = girder_client.cli.GirderCli(**gcopts)
    gc.progressReporterCls = girder_client._NoopProgressReporter
    return gc


def find_or_create_path(gc, path, dryrun):
    """
    Find the resource associated with a Girder resource path.  If it doesn't
    exist, create parent collections and folders as needed so that it does.

    :param gc: authenticated girder client.
    :param path: the path to locate or create.
    :param dryrun: if True, don't actually create anything.
    """
    try:
        doc = gc.get('resource/lookup', parameters={'path': path})
        return doc
    except girder_client.HttpError:
        pass
    parts = path.strip(os.path.sep).split(os.path.sep)
    last = None
    for plen in range(2, len(parts) + 1):
        subpath = os.path.sep.join(parts[:plen])
        try:
            doc = gc.get('resource/lookup', parameters={'path': subpath})
            last = doc
            continue
        except girder_client.HttpError:
            pass
        if plen == 2 and parts[0] == 'collection':
            # Public
            logger.info(f'Creating collection {parts[plen - 1]}')
            if not dryrun:
                last = gc.createCollection(parts[plen - 1], '', True)
                last['_modelType'] = 'collection'
        else:
            logger.info(f'Creating folder {subpath}')
            if not dryrun:
                last = gc.createFolder(
                    last['_id'], parts[plen - 1], '', last.get('_modelType', 'folder'), True, True)
        doc = last
    return doc


def zip_to_file(zf, name, path):
    """
    Extract a single file from a zipfile and store it as a local file.

    :param zf: an open zipfile.
    :param name: a name of a file within the zipfile.
    :param path: the path to extract the file to.
    """
    with zf.open(name, 'r') as src:
        with open(path, 'wb') as dest:
            while True:
                data = src.read(65536)
                if not len(data):
                    break
                dest.write(data)


def put_folders(gc, manifest, path, dryrun):
    """
    Create folders for a demo set.  This is idempotent.

    :param gc: authenticated girder client.
    :param manifest: the manifest listing the folders.
    :param path: the base girder resource path for placement.
    :param dryrun: if True, don't actually create anything.
    """
    for fidx, folder in enumerate(manifest['folder']):
        parent = find_or_create_path(
            gc, parentpath := os.path.join(path, folder['parent']), dryrun)
        logger.info(f'Creating folder {fidx + 1}/{len(manifest["folder"])} '
                    f'{parentpath}/{folder["name"]}')
        if not dryrun:
            folder['doc'] = gc.createFolder(
                parent['_id'], folder['name'],
                folder.get('description') or '',
                parent.get('_modelType', 'folder'), True, True)
            if len(folder.get('metadata', {})):
                gc.post(
                    f'folder/{folder["doc"]["_id"]}/metadata',
                    data=json.dumps(folder['metadata'], separators=(',', ':')),
                    headers={'X-HTTP-Method': 'PUT', 'Content-Type': 'application/json'})


def put_items(gc, manifest, path, dryrun):
    """
    Create items for a demo set.  This is idempotent.

    :param gc: authenticated girder client.
    :param manifest: the manifest listing the items.
    :param path: the base girder resource path for placement.
    :param dryrun: if True, don't actually create anything.
    """
    for iidx, item in enumerate(manifest['item']):
        parent = find_or_create_path(
            gc, parentpath := os.path.join(path, item['parent']), dryrun)
        logger.info(f'Creating item {iidx + 1}/{len(manifest["item"])} '
                    f'{parentpath}/{item["name"]}')
        if not dryrun:
            item['doc'] = gc.createItem(
                parent['_id'], item['name'], item['description'], True)
            if len(item.get('metadata', {})):
                gc.post(
                    f'item/{item["doc"]["_id"]}/metadata',
                    data=json.dumps(item['metadata'], separators=(',', ':')),
                    headers={'X-HTTP-Method': 'PUT', 'Content-Type': 'application/json'})


@functools.lru_cache()
def get_sha512(path):
    sha = hashlib.sha512()
    with open(path, 'rb') as f:
        while True:
            data = f.read(65536)
            if not data:
                break
            sha.update(data)
    sha = sha.hexdigest()
    return sha


def put_files(gc, manifest, path, dryrun, tempdir, zf, imported=None):
    """
    Upload files for a demo set.  This is idempotent.

    :param gc: authenticated girder client.
    :param manifest: the manifest listing the files.
    :param path: the base girder resource path for placement.
    :param dryrun: if True, don't actually create anything.
    :param tempdir: a temporary directory for extracting files from the
        zipfile.
    :param zf: an open zipfile.
    :param imported: if not None, a colon delimited specification to import
        rather than upload files of the form (local path):(assetstore id):
        (girder path).
    """
    if imported and not dryrun:
        localpath, assetstoreId, remotepath = imported.split(':')
    else:
        imported = None
    for fidx, file in enumerate(manifest['file']):
        parentpath = os.path.join(path, file['parent'])
        logger.info(f'Creating file {fidx + 1}/{len(manifest["file"])} '
                    f'{parentpath}/{file["name"]}')
        if not dryrun:
            item = gc.get('resource/lookup', parameters={'path': parentpath})
            temppath = os.path.join(tempdir, 'datafile')
            zip_to_file(zf, file['localpath'], temppath)
            fileId, current = gc.isFileCurrent(item['_id'], file['name'], temppath)
            if fileId is not None and current:
                file['doc'] = gc.getFile(fileId)
            else:
                file['doc'] = gc.uploadFileToItem(
                    item['_id'], temppath, mimeType=file['mimeType'],
                    filename=file['name'])
                if imported:
                    os.makedirs(localpath, exist_ok=True)
                    destname = file['name']
                    destbase, destext = os.path.splitext(destname)
                    destpath = os.path.join(localpath, destname)
                    tempsha = get_sha512(temppath)
                    num = 0
                    while os.path.exists(destpath):
                        if get_sha512(destpath) == tempsha:
                            break
                        num += 1
                        destname = f'{destbase} ({num}){destext}'
                        destpath = os.path.join(localpath, destname)
                    shutil.copy(temppath, destpath)
                    gc.post(f'file/{file["doc"]["_id"]}/import/adjust_path', parameters={
                        'path': os.path.join(remotepath, destname)})
            os.unlink(temppath)


def put_mark_large_images(gc, manifest):
    """
    Mark images in a demo set as large images as appropriate.

    :param gc: authenticated girder client.
    :param manifest: the manifest listing the items.
    """
    for iidx, item in enumerate(manifest['item']):
        if 'largeImage' in item:
            fileId = None
            for file in manifest['file']:
                if item['largeImage'] == file['originalId']:
                    fileId = file['doc']['_id']
                    break
            if fileId:
                item['doc'] = gc.getItem(item['doc']['_id'])
                if item['doc'].get('largeImage', {}).get('fileId') == fileId:
                    continue
                logger.info(f'Marking large image {iidx + 1}/{len(manifest["item"])} '
                            f'{item["name"]}')
                try:
                    gc.delete(f'item/{item["doc"]["_id"]}/tiles')
                except Exception:
                    pass
                gc.post(f'item/{item["doc"]["_id"]}/tiles', parameters={'fileId': fileId})


def put_annotations(gc, manifest, path, dryrun, tempdir, zf):  # noqa
    """
    Upload annotations for a demo set.  If the annotation is smaller than a
    certain size, it is posted directly to the item.  Larger annotations are
    uploaded as files with references to their parent and take some time to be
    ingested into the system.  This attempts to be idempotent based on
    annotation names, but since those do not have to be unique it is measured
    by counting matching names.

    :param gc: authenticated girder client.
    :param manifest: the manifest listing the annotations.
    :param path: the base girder resource path for placement.
    :param dryrun: if True, don't actually create anything.
    :param tempdir: a temporary directory for extracting annotations from the
        zipfile.
    :param zf: an open zipfile.
    """
    for aidx, annot in enumerate(manifest['annotation']):
        try:
            item = gc.get('resource/lookup',
                          parameters={'path': os.path.join(path, annot['parent'])})
        except Exception:
            if dryrun:
                continue
            raise
        count = len([a for a in manifest['annotation'][:aidx + 1]
                     if a['name'] == annot['name'] and a['parent'] == annot['parent']])
        annotList = gc.get('annotation', parameters={
            'itemId': item['_id'], 'name': annot['name'], 'limit': 0})
        if len(annotList) >= count:
            continue
        filename = os.path.basename(annot['localpath'])
        temppath = os.path.join(tempdir, filename)
        zip_to_file(zf, annot['localpath'], temppath)
        logger.info(f'Creating annotation {aidx + 1}/{len(manifest["annotation"])} '
                    f'for {item["name"]}')
        if dryrun:
            continue
        if annot.get('hasGirderReference'):
            record = json.load(open(temppath))
            for el in record['elements']:
                if 'girderId' in el:
                    for matched in manifest['item']:
                        if matched['originalId'] == el['girderId']:
                            el['girderId'] = matched['doc']['_id']
                            break
                    else:
                        msg = 'No matching uploaded girderId'
                        raise Exception(msg)
            json.dump(record, open(temppath, 'w'))
        if 'largeImage' in item and os.path.getsize(temppath) > 1024 ** 2:
            userId = None
            user = gc.get('user/me')
            if user:
                userId = user['_id']
            else:
                token = gc.get('token/current')
                if token:
                    userId = token['userId']
            gc.uploadFileToItem(
                item['_id'], temppath, mimeType='application/json',
                filename=filename,
                reference=json.dumps({
                    'identifier': 'LargeImageAnnotationUpload',
                    'itemId': item['_id'],
                    'fileId': item['largeImage']['fileId'],
                    'userId': userId,
                }, separators=(',', ':')))
        else:
            gc.post('annotation/item/%s' % item['_id'], data=open(temppath, 'rb').read())
        os.unlink(temppath)


def wait_for_job(gc, job):
    """
    Wait for a job to complete.

    :param gc: the girder client.
    :param job: a girder job.
    :return: the updated girder job.
    """
    lastdot = time.time()
    jobId = job['_id']
    while job['status'] not in (3, 4, 5):
        if time.time() - lastdot >= 5:
            logger.debug('.')
            lastdot = time.time()
        time.sleep(0.25)
        job = gc.get('job/%s' % jobId)
    if job['status'] == 3:
        logger.debug(' done')
    else:
        logger.error(' failed')
    return job


def put_clis(gc, manifest, dryrun):  # noqa
    """
    Upload docker image clis.

    :param gc: authenticated girder client.
    :param manifest: the manifest listing the clis.
    :param dryrun: if True, don't actually create anything.
    """
    if manifest.get('cli') is None:
        return
    for cli in manifest['cli']:
        logger.info('Adding cli %s ' % cli)
        gc.put('slicer_cli_web/docker_image', data={'name': '["%s"]' % cli})
        job = gc.get('job/all', parameters={
            'sort': 'created', 'sortdir': -1,
            'types': '["slicer_cli_web_job"]',
            'limit': 1})[0]
        wait_for_job(gc, job)


def put_demo_set(gc, demo, path, dryrun=False, imported=None):
    """
    Add a demo set to a Girder server.

    :param gc: authenticated girder client.
    :param demo: a file path or URL of the demo set zip file.
    :param path: the destination Girder resource path to upload the demo to.
    :param dryrun: if True, report what would be done without doing it.
    :param imported: if not None, a colon delimited specification to import
        rather than upload files of the form (local path):(assetstore id):
        (girder path).
    """
    with tempfile.TemporaryDirectory() as tempdir:
        if not os.path.exists(demo):
            dest = os.path.join(tempdir, 'temp.zip')
            logger.info(f'Downloading {demo}')
            with requests.get(demo, stream=True) as r:
                r.raise_for_status()
                with open(dest, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=65536):
                        f.write(chunk)
            demo = dest
        with zipfile.ZipFile(demo, 'r') as zf:
            manifest = yaml.safe_load(zf.read('manifest.yaml'))
            if manifest.get('name'):
                logger.info(f'Name: {manifest["name"]}')
            if manifest.get('description'):
                logger.info('Description:')
                logger.info(manifest['description'])
            path = path or manifest['destination']
            put_folders(gc, manifest, path, dryrun)
            put_items(gc, manifest, path, dryrun)
            put_files(gc, manifest, path, dryrun, tempdir, zf, imported)
            if not dryrun:
                put_mark_large_images(gc, manifest)
            put_annotations(gc, manifest, path, dryrun, tempdir, zf)
            put_clis(gc, manifest, dryrun)


def create_add_item(gc, zf, manifest, folder, item, base_path, filter=None):
    """
    Add an item all of its files to a demo set.

    :param gc: authenticated girder client.
    :param zf: open zipfile.
    :param manifest: the manifest record to modify.
    :param folder: the parent folder of the item.
    :param item: the girder item document to add.
    :param base_path: the girder resource path to use as the context of
        relative paths.
    :param filter: an optional regex that must validate to store the item.
    """
    if '_modelType' in folder:
        folder_path = gc.get(f'resource/{folder.get("_id", folder.get("originalId"))}/path',
                             parameters={'type': folder['_modelType']})
        parent_path = (folder_path[len(base_path):].strip('/')
                       if folder_path.startswith(base_path) else
                       os.path.join(folder['parent'], folder['name']).strip('/'))
    else:
        parent_path = os.path.join(folder['parent'], folder['name']).strip('/')
    dirname = f'item{len(manifest["item"])}'
    item_path = gc.get(f'resource/{item["_id"]}/path', parameters={'type': 'item'})
    item_path = (item_path[len(base_path):].strip('/')
                 if item_path.startswith(base_path) else
                 os.path.join(parent_path, item['name']).strip('/'))
    if filter and not re.search(filter, item_path):
        logger.debug('Filtering out %s', item_path)
        return
    logger.debug(f'Adding item {len(manifest["item"]) + 1} {parent_path}/{item["name"]}')
    manifest['item'].append({
        'model': 'item',
        'parent': parent_path,
        'name': item['name'],
        'description': item.get('description'),
        'localpath': dirname,
        'originalId': item['_id'],
        'metadata': item.get('meta', {}),
    })
    if 'largeImage' in item and 'expected' not in item['largeImage']:
        manifest['item'][-1]['largeImage'] = item['largeImage']['fileId']
    zf.mkdir(dirname)
    with tempfile.TemporaryDirectory() as tempdir:
        for file in gc.listFile(item['_id']):
            logger.info(f'Adding file {parent_path}/{item["name"]}/{file["name"]}')
            zfpath = os.path.join(dirname, file['name'])
            temppath = os.path.join(tempdir, file['name'])
            gc.downloadFile(file['_id'], temppath)
            manifest['file'].append({
                'model': 'file',
                'parent': item_path,
                'name': file['name'],
                'mimeType': file['mimeType'],
                'localpath': zfpath,
                'originalId': file['_id'],
            })
            zf.write(temppath, zfpath)


def create_add_annotations(gc, zf, manifest, base_path):
    """
    Add annotations for all items in a demo set.  This may add additional
    items (their annotations are not added) and possibly an additional folder
    to store them.

    :param gc: authenticated girder client.
    :param zf: open zipfile.
    :param manifest: the manifest record to modify.
    :param base_path: the girder resource path to use as the context of
        relative paths.
    """
    with tempfile.TemporaryDirectory() as tempdir:
        temppath = os.path.join(tempdir, 'annotations.json')
        for item in manifest['item'][:]:
            item_path = gc.get(f'resource/{item["originalId"]}/path',
                               parameters={'type': 'item'})
            parent_path = (item_path[len(base_path):].strip('/')
                           if item_path.startswith(base_path) else item_path)
            annotList = gc.get('annotation', parameters={
                'itemId': item['originalId'], 'limit': 0})
            if not len(annotList):
                continue
            for aidx, annot in enumerate(annotList):
                zfpath = os.path.join(item['localpath'], f'_annotation_{aidx}.json')
                logger.info(f'Getting annotation {aidx}/{len(annotList)} for {item["name"]}')
                hasGirder = False
                with open(temppath, 'wb') as f:
                    record = gc.get(f'annotation/{annot["_id"]}')
                    record = record.get('annotation', record)
                    logger.debug(f'Adding annotation {record["name"]}')
                    f.write(json.dumps(record, separators=(',', ':')).encode())
                    for el in record.get('elements', [])[:10]:
                        hasGirder = bool(hasGirder or el.get('girderId'))
                        if (el.get('girderId') and el['girderId'] not in
                                {i['originalId'] for i in manifest['item']}):
                            folderName = '_annotations'
                            folderParent = parent_path.split('/')[0]
                            folder = [f for f in manifest['folder']
                                      if f['parent'] == folderParent and
                                      f['name'] == folderName]
                            if not len(folder):
                                manifest['folder'].append({
                                    'model': 'folder',
                                    'parent': folderParent,
                                    'name': folderName,
                                })
                                folder = manifest['folder'][-1]
                            else:
                                folder = folder[0]
                            annItem = gc.getItem(record['elements'][0]['girderId'])
                            create_add_item(gc, zf, manifest, folder, annItem, base_path)
                    manifest['annotation'].append({
                        'name': record['name'],
                        'parent': os.path.join(item['parent'], item['name']),
                        'localpath': zfpath,
                    })
                if hasGirder:
                    manifest['annotation'][-1]['hasGirderReference'] = True
                zf.write(temppath, zfpath)


def create_add_folder(gc, zf, manifest, folder, max_items, base_path, filter):
    """
    Add a folder and all of its subfolders and items to a demo set.

    :param gc: authenticated girder client.
    :param zf: open zipfile.
    :param manifest: the manifest record to modify.
    :param folder: the folder document to add to the demo set.
    :param max_items: if non-zero, stop after this many primary items are
        added.
    :param base_path: the girder resource path to use as the context of
        relative paths.
    :param filter: an optional regex that must validate to store the folder.
    """
    folder_path = gc.get(f'resource/{folder["_id"]}/path',
                         parameters={'type': folder['_modelType']})
    parent_path = (folder_path[len(base_path):].strip('/')
                   if folder_path.startswith(base_path) else folder_path)
    if filter and not re.search(filter, parent_path):
        logger.debug('Filtering out %s', parent_path)
        return
    if max_items and len(manifest['item']) >= max_items:
        return
    if folder['_modelType'] == 'folder':
        for item in gc.listItem(folder['_id']):
            if max_items and len(manifest['item']) >= max_items:
                return
            create_add_item(gc, zf, manifest, folder, item, base_path, filter)
    for subfolder in gc.listFolder(folder['_id'], folder['_modelType']):
        if max_items and len(manifest['item']) >= max_items:
            return
        folder_path = f'{parent_path}/{subfolder["name"]}'
        if filter and not re.search(filter, folder_path):
            logger.debug('Filtering out %s', folder_path)
            continue
        logger.debug(f'Adding folder {parent_path}/{subfolder["name"]}')
        manifest['folder'].append({
            'model': 'folder',
            'parent': parent_path,
            'name': subfolder['name'],
            'description': subfolder.get('description'),
            'metadata': subfolder.get('meta', {}),
        })
        create_add_folder(gc, zf, manifest, subfolder, max_items, base_path, filter)


def create_demo_set(gc, resource_path, target_path, dest_path, max_items=0,
                    filter=None, cli=None, name=None, description=None,
                    overwrite=False):
    """
    Create a zip file containing a manifest file, data files, and annotation
    files.

    :param gc: authenticated girder client.
    :param resource_path: location of the girder server to download.
    :param target_path: recommended girder resource path for uploads.
    :param dest_path: path for the output zip file.
    :param max_items: if non-zero, stop after this many primary items are
        added.  There may be more items than this in order to have complete
        annotations.
    :param filter: if not None, a regex that is applied to resource paths
        during creation.  Only sub resource paths below the containing document
        that validate with this regex are added.
    :param overwrite: if False and dest_path exists, raise an error.
    """
    resource_path = resource_path.rstrip('/')
    folder = gc.get('resource/lookup', parameters={'path': resource_path})
    if folder['_modelType'] not in {'folder', 'collection'}:
        msg = 'A demo set can only be made from a folder or collection.'
        raise Exception(msg)
    base_path = os.path.dirname(gc.get(f'resource/{folder["_id"]}/path',
                                parameters={'type': folder['_modelType']}))
    logger.debug(f'Adding folder {folder["name"]}')
    manifest = {
        'name': name or f'Demo Set of {folder["name"]}',
        'description': description or '',
        'destination': os.path.dirname(target_path or resource_path),
        'folder': [{
            'model': folder['_modelType'],
            'parent': '',
            'name': folder['name'],
            'description': folder.get('description'),
            'originalId': folder['_id'],
            'metadata': folder.get('meta', {}),
        }],
        'item': [],
        'file': [],
        'annotation': [],
        'cli': cli if cli else [],
    }
    with zipfile.ZipFile(
            dest_path, 'w' if overwrite else 'x',
            compression=zipfile.ZIP_DEFLATED) as zf:
        create_add_folder(gc, zf, manifest, folder, max_items, base_path, filter)
        create_add_annotations(gc, zf, manifest, base_path)
        orig = os.path.basename(resource_path)
        dest = os.path.basename(target_path or resource_path)
        if orig != dest and orig == manifest['folder'][0]['name']:
            manifest['folder'][0]['name'] = dest
            for rtype in {'folder', 'item', 'file', 'annotation'}:
                for record in manifest[rtype]:
                    if record['parent'].split(os.path.sep)[0] == orig:
                        record['parent'] = os.path.sep.join(
                            [dest] + record['parent'].split(os.path.sep)[1:])
        if not manifest['description']:
            if 'item' in manifest:
                manifest['description'] = f'{len(manifest["item"])} items'
            else:
                manifest['description'] = ''
        zf.writestr('manifest.yaml', yaml.dump(
            manifest, Dumper=IndentDumper, default_flow_style=False, sort_keys=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Add a set of demo images with a folder structure, '
        'metadata, and annotations to a Girder server.  This can also create '
        'such a set of images from a Girder server.')
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
    parser.add_argument(
        '--verbose', '-v', action='count', default=0, help='Increase verbosity')
    parser.add_argument(
        '--silent', '-s', action='count', default=0, help='Decrease verbosity')
    # This program's options
    parser.add_argument(
        '--path', help='Destination resource path.  A folder of sample images '
        'will be created here.  This must be a folder or collection.  When '
        'creating a demo, this specifies the default destination path; if '
        'unset, it will be the create path.')
    parser.add_argument(
        '--imported', help='Instead of uploading data files, store them in a '
        'local directory and import them.  This requires using an admin user '
        'to perform the import.  The parameter is a colon separated field of '
        'the form (local path for storage):(assetstore id):(girder path for '
        'import).  All files are stored in the same directory with some basic '
        'name deduplication.')
    parser.add_argument(
        'demo', help='A zip file with the demo file set.  When adding a demo '
        'set to a system this may be a URL.')
    parser.add_argument(
        '--dry-run', '-n', action='store_true', help='Report what would be '
        'uploaded, but do not actually do anything.  This has no effect when '
        'creating a demo set.')
    parser.add_argument(
        '--create', help='Create a demo set.  This is the resource path of '
        'the containing folder, user, or collection and the demo file is the '
        'destination file (it cannot be a URL).')
    parser.add_argument(
        '--name', help='Add a name when creating a demo set.')
    parser.add_argument(
        '--description', help='Add a description when creating a demo set.')
    parser.add_argument(
        '--filter', help='A regex that is applied to resource paths during '
        'creation.  Only sub resource paths below the containing document '
        'that validate with this regex are added.')
    parser.add_argument(
        '--max-files', type=int, help='The maximum number of files to add '
        'when creating a demo set.  Default is unlimited.')
    parser.add_argument(
        '--cli', action='append', help='A slicer_cli_web cli docker image to '
        'include in a created manifest.')
    parser.add_argument(
        '--overwrite', '-y', action='store_true',
        help='Allow overwriting an existing output file.')
    opts = parser.parse_args()
    logger.setLevel(max(1, logging.WARNING - (opts.verbose - opts.silent) * 10))
    logger.addHandler(logging.StreamHandler(sys.stderr))
    logger.debug('Parsed arguments: %r', opts)
    gc = get_girder_client(vars(opts))

    if opts.create:
        create_demo_set(gc, opts.create, opts.path, opts.demo, opts.max_files,
                        opts.filter, opts.cli, opts.name, opts.description,
                        opts.overwrite)
    else:
        put_demo_set(gc, opts.demo, opts.path, opts.dry_run, opts.imported)
