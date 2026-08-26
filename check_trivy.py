#!/usr/bin/env python3

import argparse
import json
import os

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Check the json output of trivy against a trivy ignore '
        'file, listing what can be removed or must be added.')
    parser.add_argument(
        'json', help='The json output from trivy.  This would be the output '
        'of a command line `trivy image --scanners vuln --input docker.tar '
        '--exit-code 1 --severity HIGH,CRITICAL --no-progress --ignorefile '
        '/dev/null --format json`')
    parser.add_argument('ignore', help='The trivy ignore file to compare.')
    parser.add_argument('--update', action='store_true', help='Modify the trivy file.')
    args = parser.parse_args()
    results = json.load(open(args.json))
    if os.path.exists(args.ignore):
        current = {line.strip().split('#')[0]
                   for line in open(args.ignore).readlines()
                   if line.strip() and not line.strip().startswith('#')}
    else:
        current = set()
    newset = set()
    reasons = {}
    for res in results['Results']:
        if 'Vulnerabilities' not in res:
            continue
        for vuln in res['Vulnerabilities']:
            id = vuln['VulnerabilityID']
            newset.add(id)
            reasons[id] = {
                'severity': vuln['Severity'],
                'title': vuln.get('Title', id),
                'type': res['Type'],
            }
    unneeded = current - newset
    if len(unneeded):
        print('These CVEs can be removed:')
        for id in sorted(unneeded):
            print(f'  {id}')
    needed = newset - current
    if len(needed):
        print('These CVEs must be added:')
        for id in sorted(needed):
            print(f'  {id}')
    new = []
    for id in sorted(newset, key=lambda a: (reasons[a]['type'], a)):
        new.append(
            f'# {reasons[id]["severity"]}: {reasons[id]["type"]} - {reasons[id]["title"]}'[:79]
            .rstrip())
        new.append(f'{id}')
    print('New ignore file:')
    print('\n'.join(new))
    if os.path.exists(args.ignore) and args.update:
        current = open(args.ignore).read()
        if '\n\n' in current:
            current = current.rsplit('\n\n', 1)[0] + '\n\n'
        else:
            current = ''
        current += '\n'.join(new) + '\n'
        with open(args.ignore, 'w') as fptr:
            fptr.write(current)
