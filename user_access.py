#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "girder-client",
# ]
# ///

import argparse
import os

import girder_client
import girder_client.cli

girder_client.DEFAULT_PAGE_LIMIT = 50000


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


def get_user_list(gc, userids):
    userids = set(userids or [])
    allusers = not len(userids)
    userlist = []
    for user in gc.listUser():
        if allusers:
            userlist.append(user)
        elif user['login'] in userids:
            userlist.append(user)
            userids.remove(user['login'])
        elif user['_id'] in userids:
            userlist.append(user)
            userids.remove(user['_id'])
        elif user['email'] in userids:
            userlist.append(user)
            userids.remove(user['email'])
        elif f'{user["firstName"]} {user["lastName"]}' in userids:
            userlist.append(user)
            userids.remove(f'{user["firstName"]} {user["lastName"]}')
    return sorted(userlist, key=lambda u: u['login'])


def levelName(level):
    return {0: 'Read ', 1: 'Write', 2: 'Admin'}.get(level, f'{level:<5d}')


def user_access_users(gc, userid, verbose):
    users = []
    for user in gc.listResource('user', params={'sort': 'name'}):
        user = gc.get(f'resource/{user["_id"]}', parameters={'type': 'user'})
        entry = [u for u in user.get('access', {}).get('users', []) if u['id'] == userid]
        if not len(entry):
            continue
        entry = entry[0]
        users.append((entry.get('level', 0), user['login'], user))
    if len(users):
        print('  Users:')
        for level, name, _user in sorted(users):
            print(f'    {levelName(level)} {name}')
    return users


def user_access_groups(gc, userid, verbose):
    groups = []
    for group in gc.listResource('group', params={'sort': 'name'}):
        group = gc.get(f'resource/{group["_id"]}', parameters={'type': 'group'})
        entry = [u for u in group.get('access', {}).get('users', []) if u['id'] == userid]
        if not len(entry):
            continue
        entry = entry[0]
        groups.append((entry.get('level', 0), group['name'], group))
    if len(groups):
        print('  Groups:')
        for level, name, _group in sorted(groups):
            print(f'    {levelName(level)} {name}')
    return groups


def user_access_collections(gc, userid, verbose):
    cols = []
    for col in gc.listCollection():
        col = gc.get(f'resource/{col["_id"]}', parameters={'type': 'collection'})
        entry = [u for u in col.get('access', {}).get('users', []) if u['id'] == userid]
        if not len(entry):
            continue
        entry = entry[0]
        cols.append((entry.get('level', 0), col['name'], col))
    if len(cols):
        print('  Collections:')
        for level, name, _col in sorted(cols):
            print(f'    {levelName(level)} {name}')
    return cols


def user_access_folders(gc, userid, verbose, parentId=None, parentType=None):
    folders = []
    if parentId:
        for folder in gc.listFolder(parentId, parentType):
            folder = gc.get(f'resource/{folder["_id"]}', parameters={'type': 'folder'})
            entry = [u for u in folder.get('access', {}).get('users', []) if u['id'] == userid]
            if len(entry):
                entry = entry[0]
                path = gc.get(f'/resource/{folder["_id"]}/path', parameters={'type': 'folder'})
                folders.append((entry.get('level', 0), path, folder))
            folders.extend(user_access_folders(gc, userid, verbose, folder['_id'], 'folder'))
    else:
        for col in gc.listCollection():
            folders.extend(user_access_folders(gc, userid, verbose, col['_id'], 'collection'))
        for user in gc.listUser():
            folders.extend(user_access_folders(gc, userid, verbose, user['_id'], 'user'))
        if len(folders):
            print('  Folders:')
            for level, path, _folder in sorted(folders):
                print(f'    {levelName(level)} {path}')
    return folders


def user_access_annotations(gc, userid, verbose, parentId=None, parentType=None):
    annots = []
    items = {}
    if parentId:
        for folder in gc.listFolder(parentId, parentType):
            for annot in gc.listResource(f'annotation/folder/{folder["_id"]}',
                                         params={'recurse': True}):
                entry = [u for u in annot.get('access', {}).get('users', []) if u['id'] == userid]
                if len(entry):
                    itemid = annot['itemId']
                    entry = entry[0]
                    if itemid not in items:
                        items[itemid] = gc.get(
                            f'/resource/{itemid}/path', parameters={'type': 'item'})
                    annots.append((
                        entry.get('level', 0), items[itemid],
                        annot['annotation']['name'], annot['_version'], annot['_id'], annot))
    else:
        for col in gc.listCollection():
            annots.extend(user_access_annotations(gc, userid, verbose, col['_id'], 'collection'))
        for user in gc.listUser():
            annots.extend(user_access_annotations(gc, userid, verbose, user['_id'], 'user'))
        if len(annots):
            print('  Annotations:')
            for level, path, name, version, _id, _annot in sorted(annots):
                print(f'    {levelName(level)} {path} {name} {version}')
    return annots


def user_access(gc, user, verbose):
    userid = user['_id']
    user_access_users(gc, userid, verbose)
    user_access_groups(gc, userid, verbose)
    user_access_collections(gc, userid, verbose)
    user_access_folders(gc, userid, verbose)
    try:
        user_access_annotations(gc, userid, verbose)
    except Exception:
        raise
        pass


if __name__ == '__main__':  # noqa
    parser = argparse.ArgumentParser(
        description='Show what groups, collections, folders, users, and large '
        'image annotations a user has access to and their access level.')
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
        '--userid', '-u', action='append',
        help='A user to analyze.  If not specified, all users will be used. '
        'is can either be a user id OR a mongo ID for the user.')

    args = parser.parse_args()
    if args.verbose >= 2:
        print('Parsed arguments: %r' % args)
    gc = get_girder_client(vars(args))
    userlist = get_user_list(gc, args.userid)
    for user in userlist:
        print(f'User: {user["login"]}')
        user_access(gc, user, args.verbose)


# TODO:
#  - show publicly accessible resources
#  - show what groups the user blongs to
#  - include user's group access in the search
#  - add edit annotation flags
#  - search for a group rather than a user
#  - show tokens from a user
#  - any sort of progress to make this more bearable
