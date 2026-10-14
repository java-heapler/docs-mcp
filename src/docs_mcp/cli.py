"""JSON CLI for Google Docs. Mutations preview unless explicitly confirmed."""
import argparse
import json
import sys
from pathlib import Path

from . import auth
from .client import DocsClient, DocsError

MAX_JSON_BYTES = 2 * 1024 * 1024


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise DocsError('Invalid command arguments. Use --help for usage.')


def _reject_constant(value):
    raise ValueError('Nonfinite JSON')


def load_json(path):
    try:
        with Path(path).open('rb') as stream:
            data = stream.read(MAX_JSON_BYTES + 1)
        if len(data) > MAX_JSON_BYTES:
            raise DocsError('JSON file exceeds the 2 MiB limit.')
        return json.loads(data, parse_constant=_reject_constant)
    except (OSError, UnicodeError, ValueError, RecursionError):
        raise DocsError('Cannot read a valid finite JSON file.') from None


def parser():
    root = Parser(prog='google-docs', description=__doc__)
    commands = root.add_subparsers(dest='command', required=True)
    commands.add_parser('doctor')
    commands.add_parser('mcp')
    login = commands.add_parser('auth').add_subparsers(dest='auth_command', required=True).add_parser('login')
    login.add_argument('--client-secrets', required=True)
    login.add_argument('--token-file')
    for name in ('get', 'text', 'create', 'batch', 'insert', 'replace'):
        cmd = commands.add_parser(name)
        cmd.add_argument('title' if name == 'create' else 'document_id')
        if name == 'batch':
            cmd.add_argument('--requests', required=True, help='Path to a JSON array of Docs API requests.')
        if name in ('insert', 'replace'):
            cmd.add_argument('--text', required=True)
            cmd.add_argument('--tab', required=True)
        if name == 'insert':
            cmd.add_argument('--index', type=int, default=1, help='UTF-16 code-unit index.')
        if name == 'replace':
            cmd.add_argument('--replacement', required=True)
            cmd.add_argument('--ignore-case', action='store_true')
        if name in ('batch', 'insert', 'replace'):
            cmd.add_argument('--revision')
        if name not in ('get', 'text'):
            cmd.add_argument('--confirm', action='store_true', help='Execute only with user authorization.')
    return root


def dispatch(args):
    if args.command == 'doctor':
        return auth.doctor()
    if args.command == 'auth':
        return auth.login(args.client_secrets, token_path=args.token_file)
    if args.command == 'mcp':
        from .mcp_server import run
        run()
        return None
    client = DocsClient()
    if args.command == 'get':
        return client.get_document(args.document_id)
    if args.command == 'text':
        return client.read_text(args.document_id)
    if args.command == 'create':
        return client.create_document(args.title, confirm=args.confirm)
    if args.command == 'batch':
        return client.batch_update(args.document_id, load_json(args.requests), required_revision_id=args.revision, confirm=args.confirm)
    if args.command == 'insert':
        return client.insert_text(args.document_id, args.text, args.tab, index=args.index, required_revision_id=args.revision, confirm=args.confirm)
    return client.replace_text(args.document_id, args.text, args.replacement, args.tab, match_case=not args.ignore_case, required_revision_id=args.revision, confirm=args.confirm)


def main(argv=None):
    try:
        result = dispatch(parser().parse_args(argv))
        if result is not None:
            print(json.dumps(result, ensure_ascii=False, allow_nan=False))
        return 0
    except DocsError as exc:
        print(json.dumps({'error': str(exc)}), file=sys.stderr)
        return 2
    except Exception:
        print(json.dumps({'error': 'Operation failed. Check configuration and permissions; do not blindly retry writes.'}), file=sys.stderr)
        return 1
