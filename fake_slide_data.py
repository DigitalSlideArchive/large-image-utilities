#!/usr/bin/env python3

# pip install girder_client fake_biology

import argparse
import os
import random
import time

import faker
import faker_biology.physiology
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
    return girder_client.cli.GirderCli(**gcopts)


def make_func(fake, value, fieldtype, typeval):
    if hasattr(fake, value):
        return getattr(fake, value)
    return {
        'range': lambda: random.randint(int(typeval[0]), int(typeval[1])),
        'floatrange': lambda: random.uniform(float(typeval[0]), float(typeval[1])),
        'enum': lambda: random.choice(typeval)
    }[fieldtype]


if __name__ == '__main__':  # noqa
    parser = argparse.ArgumentParser(
        description='Add fake data to a folder of large images.')
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
    parser.add_argument(
        '--field', action='append',
        help='(Field name):(Field Type).  Field type is one of "organelle", '
        '"celltype", "range:(low),(high)", "floatrange:(low),(high)", '
        '"enum:(comma separated list)".')
    parser.add_argument(
        '--annotation', help='(chance[0-1]),(min points),(max points),(iterations)')

    args = parser.parse_args()
    if args.verbose >= 2:
        print('Parsed arguments: %r' % args)
    fake = faker.Faker()
    fake.add_provider(faker_biology.physiology.CellType)
    fake.add_provider(faker_biology.physiology.Organ)
    fake.add_provider(faker_biology.physiology.Organelle)
    annot = None
    if args.annotation:
        annot = args.annotation.split(',')
        annot = float(annot[0]), int(annot[1]), int(annot[2]), int(annot[3])
    fields = {}
    for field in (args.field or []):
        key, value = field.split(':', 1)
        fieldtype, typeval = value.split(':', 1) if ':' in value else (value, None)
        if typeval:
            typeval = typeval.split(',')
        fields[key] = make_func(fake, value, fieldtype, typeval)

    client = get_girder_client(vars(args))
    for item in client.listItem(args.folder):
        print(item['name'])
        try:
            limetadata = client.get('item/%s/tiles' % item['_id'])
        except Exception:
            continue
        metadata = {}
        for field, func in fields.items():
            metadata[field] = func()
        if len(metadata):
            print(metadata)
            client.addMetadataToItem(item['_id'], metadata=metadata)
        counts = [0, 0]
        if annot:
            for _ in range(annot[3]):
                if random.random() <= annot[0]:
                    record = {
                        'name': 'Annotation %s' % time.strftime('%Y-%m-%d %H:%M:%S'),
                        'description': '',
                        'elements': [{
                            'lineColor': 'rgb(0,0,0)',
                            'lineWidth': 2,
                            'fillColor': 'rgba(0,0,0,0)',
                            'type': 'point',
                            'center': [
                                random.uniform(0, limetadata['sizeX']),
                                random.uniform(0, limetadata['sizeY']),
                                0,
                            ]} for _ in range(random.randint(annot[1], annot[2]))],
                    }
                    client.post('annotation', parameters={'itemId': item['_id']}, json=record)
                    counts[0] += 1
                    counts[1] += len(record['elements'])
        if counts[0]:
            print('Annotations: %d %d' % (counts[0], counts[1]))
