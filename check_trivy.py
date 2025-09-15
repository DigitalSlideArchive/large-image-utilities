#!/usr/bin/env python3

import argparse
import json

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
    args = parser.parse_args()
    results = json.load(open(args.json))
    current = {line.strip().split('#')[0]
               for line in open(args.ignore).readlines()
               if line.strip() and not line.strip().startswith('#')}
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
                'title': vuln['Title'],
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
    print('New ignore file:')
    for id in sorted(newset, key=lambda a: (reasons[a]['type'], a)):
        print(f'# {reasons[id]["severity"]}: {reasons[id]["type"]} - {reasons[id]["title"][:60]}')
        print(f'{id}')
