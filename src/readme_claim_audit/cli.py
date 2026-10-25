"""Command line interface."""
import argparse
import json
from . import __version__
from .audit import audit


def main(argv=None):
    parser = argparse.ArgumentParser(prog="readme-claim-audit")
    parser.add_argument('--version', action='version', version=__version__)
    commands = parser.add_subparsers(dest='command', required=True)
    command = commands.add_parser('audit', help='audit local README claims')
    command.add_argument('repo', nargs='?', default='.')
    command.add_argument('--json', action='store_true')
    command.add_argument('--fail-on', choices=('high', 'medium'), default='high')
    command.add_argument('--ignore', nargs='+', action='append', default=[])
    args = parser.parse_args(argv)
    try:
        result = audit(args.repo, [g for group in args.ignore for g in group], args.fail_on)
    except (ValueError, OSError) as error:
        parser.error(str(error))
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print('{verdict}: {total} findings; ignored={ignored_count}; parse errors={parse_error_count}'.format(**result))
        print('Per severity: ' + json.dumps(result['per_severity'], sort_keys=True))
        print('Per kind: ' + json.dumps(result['per_kind'], sort_keys=True))
        for finding in result['findings']:
            print('{file}:{line}: {severity} {kind}: {claim} ({detail})'.format(**finding))
        for note in result['notes']: print(note)
        if result['truncated']: print('Truncated: {} findings omitted'.format(result['omitted_count']))
    return {'PASS': 0, 'WARN': 1, 'FAIL': 2}[result['verdict']]
