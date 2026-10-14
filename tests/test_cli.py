import json
import runpy
import sys
from unittest.mock import Mock

import pytest

from docs_mcp import cli
from docs_mcp.client import DocsError


def test_dispatch_commands(monkeypatch, tmp_path):
    client = Mock()
    monkeypatch.setattr(cli, 'DocsClient', lambda: client)
    requests = tmp_path / 'requests.json'
    requests.write_text('[{"insertText":{"text":"hello","location":{"index":1}}}]')
    cases = [
        (['get', 'abc'], 'get_document', ('abc',), {}),
        (['text', 'abc'], 'read_text', ('abc',), {}),
        (['create', 'Title', '--confirm'], 'create_document', ('Title',), {'confirm': True}),
        (['batch', 'abc', '--requests', str(requests), '--revision', 'rev'], 'batch_update', ('abc', json.loads(requests.read_text())), {'required_revision_id': 'rev', 'confirm': False}),
        (['insert', 'abc', '--text', 'Hi', '--tab', 't', '--index', '2'], 'insert_text', ('abc', 'Hi', 't'), {'index': 2, 'required_revision_id': None, 'confirm': False}),
        (['replace', 'abc', '--text', 'old', '--replacement', 'new', '--tab', 't', '--ignore-case'], 'replace_text', ('abc', 'old', 'new', 't'), {'match_case': False, 'required_revision_id': None, 'confirm': False}),
    ]
    for argv, method, args, kwargs in cases:
        assert cli.dispatch(cli.parser().parse_args(argv)) is getattr(client, method).return_value
        getattr(client, method).assert_called_once_with(*args, **kwargs)


def test_auth_doctor_mcp(monkeypatch):
    from docs_mcp import mcp_server
    doctor, login, run = Mock(return_value={'local': True}), Mock(return_value={'ok': True}), Mock()
    monkeypatch.setattr(cli.auth, 'doctor', doctor)
    monkeypatch.setattr(cli.auth, 'login', login)
    monkeypatch.setattr(mcp_server, 'run', run)
    assert cli.dispatch(cli.parser().parse_args(['doctor'])) == {'local': True}
    assert cli.dispatch(cli.parser().parse_args(['auth', 'login', '--client-secrets', 'client.json', '--token-file', 'token.json'])) == {'ok': True}
    login.assert_called_once_with('client.json', token_path='token.json')
    assert cli.main(['mcp']) == 0
    run.assert_called_once_with()


def test_json_file_limits_and_errors(tmp_path):
    path = tmp_path / 'requests.json'
    for data in [b'NaN', b'Infinity', b'-Infinity', b'\xff', b'{', b'[' * 2000]:
        path.write_bytes(data)
        with pytest.raises(DocsError, match='valid finite JSON'):
            cli.load_json(path)
    path.write_bytes(b' ' * (cli.MAX_JSON_BYTES + 1))
    with pytest.raises(DocsError, match='2 MiB'):
        cli.load_json(path)
    with pytest.raises(DocsError, match='valid finite JSON'):
        cli.load_json(tmp_path / 'missing')


def test_main_json_and_sanitized_errors(monkeypatch, capsys):
    monkeypatch.setattr(cli.auth, 'doctor', lambda: {'title': '世界'})
    assert cli.main(['doctor']) == 0
    assert json.loads(capsys.readouterr().out) == {'title': '世界'}
    assert cli.main(['unknown']) == 2
    assert json.loads(capsys.readouterr().err)['error']
    monkeypatch.setattr(cli.auth, 'doctor', Mock(side_effect=RuntimeError('secret-token')))
    assert cli.main(['doctor']) == 1
    output = capsys.readouterr().err
    assert 'secret-token' not in output
    assert 'do not blindly retry' in json.loads(output)['error']


def test_module_entrypoint(monkeypatch):
    monkeypatch.setattr(cli, 'main', lambda: 0)
    with pytest.raises(SystemExit) as exit_info:
        runpy.run_module('docs_mcp', run_name='__main__')
    assert exit_info.value.code == 0
