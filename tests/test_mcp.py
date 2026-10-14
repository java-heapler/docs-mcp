import asyncio
import os
import subprocess
import sys
from unittest.mock import Mock

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.server.fastmcp.exceptions import ToolError

from docs_mcp import auth, mcp_server


def test_tools_and_annotations():
    indexed = {tool.name: tool for tool in asyncio.run(mcp_server.mcp.list_tools())}
    assert set(indexed) == {'docs_doctor', 'docs_get', 'docs_text', 'docs_create', 'docs_batch', 'docs_insert', 'docs_replace'}
    for name, tool in indexed.items():
        readonly = name in {'docs_doctor', 'docs_get', 'docs_text'}
        assert tool.annotations.readOnlyHint is readonly
        if not readonly:
            assert tool.inputSchema['properties']['confirm']['default'] is False
            assert tool.annotations.idempotentHint is False
    assert indexed['docs_doctor'].annotations.openWorldHint is False
    assert indexed['docs_replace'].annotations.destructiveHint is True


def test_forwarding(monkeypatch):
    client = Mock()
    monkeypatch.setattr(mcp_server, 'DocsClient', lambda: client)
    monkeypatch.setattr(auth, 'doctor', lambda: {'local': True})
    assert mcp_server.docs_doctor() == {'local': True}
    cases = [
        ('docs_get', ('abc',), {}, 'get_document', ('abc',), {}),
        ('docs_text', ('abc',), {}, 'read_text', ('abc',), {}),
        ('docs_create', ('Title',), {'confirm': True}, 'create_document', ('Title',), {'confirm': True}),
        ('docs_batch', ('abc', [{'deleteContentRange': {}}]), {'required_revision_id': 'rev'}, 'batch_update', ('abc', [{'deleteContentRange': {}}]), {'required_revision_id': 'rev', 'confirm': False}),
        ('docs_insert', ('abc', 'Hi', 'tab'), {'index': 7, 'required_revision_id': 'rev', 'confirm': True}, 'insert_text', ('abc', 'Hi', 'tab'), {'index': 7, 'required_revision_id': 'rev', 'confirm': True}),
        ('docs_replace', ('abc', 'old', '', 'tab'), {'match_case': False}, 'replace_text', ('abc', 'old', '', 'tab'), {'match_case': False, 'required_revision_id': None, 'confirm': False}),
    ]
    for name, args, kwargs, method, forwarded_args, forwarded_kwargs in cases:
        assert getattr(mcp_server, name)(*args, **kwargs) is getattr(client, method).return_value
        getattr(client, method).assert_called_once_with(*forwarded_args, **forwarded_kwargs)


def test_strict_types(monkeypatch):
    monkeypatch.setattr(mcp_server, 'DocsClient', lambda: pytest.fail('Invalid arguments reached client'))
    cases = [
        ('docs_get', {'document_id': 123}),
        ('docs_create', {'title': 'T', 'confirm': 'false'}),
        ('docs_create', {'title': 'T', 'confirm': 1}),
        ('docs_insert', {'document_id': 'abc', 'text': 'T', 'tab_id': 'tab', 'index': True}),
        ('docs_insert', {'document_id': 'abc', 'text': 'T', 'tab_id': 'tab', 'index': '1'}),
        ('docs_replace', {'document_id': 'abc', 'text': 'T', 'replacement': '', 'tab_id': 'tab', 'match_case': 'true'}),
        ('docs_batch', {'document_id': 'abc', 'requests': [], 'required_revision_id': 4}),
        ('docs_batch', {'document_id': 'abc', 'requests': '{}'}),
    ]
    async def check():
        for name, args in cases:
            with pytest.raises(ToolError, match='validation error'):
                await mcp_server.mcp.call_tool(name, args)
    asyncio.run(check())


def test_no_auth_for_previews(monkeypatch):
    monkeypatch.setattr(auth, 'build_service', lambda: pytest.fail('Preview attempted authentication'))
    assert mcp_server.docs_create('T')['status'] == 'preview'
    assert mcp_server.docs_batch('abc', [{'insertText': {'text': 'T', 'location': {'index': 1}}}])['status'] == 'preview'
    assert mcp_server.docs_insert('abc', 'T', 'tab')['status'] == 'preview'
    assert mcp_server.docs_replace('abc', 'T', 'U', 'tab')['status'] == 'preview'


def test_run(monkeypatch):
    run = Mock()
    monkeypatch.setattr(mcp_server.mcp, 'run', run)
    mcp_server.run()
    run.assert_called_once_with(transport='stdio')


def test_real_stdio_initialize_list_and_previews(tmp_path):
    network_attempt = tmp_path / 'network-attempt'
    guard = f"""
import sys
from pathlib import Path

def block_network(event, args):
    if event == 'socket.connect':
        Path({str(network_attempt)!r}).write_text('blocked socket.connect')
        raise RuntimeError('Network forbidden during preview test')

sys.addaudithook(block_network)
"""
    # Prove the subprocess guard blocks a connection before exercising the server.
    probe = subprocess.run(
        [sys.executable, '-c', guard + "\nimport socket; socket.socket().connect(('127.0.0.1', 9))"],
        capture_output=True, text=True, timeout=10,
    )
    assert probe.returncode != 0
    assert 'Network forbidden during preview test' in probe.stderr
    assert network_attempt.read_text() == 'blocked socket.connect'
    network_attempt.unlink()
    launcher = guard + "\nimport runpy; sys.argv = ['google-docs', 'mcp']; runpy.run_module('docs_mcp', run_name='__main__')"
    params = StdioServerParameters(command=sys.executable, args=['-c', launcher], env={
        **os.environ, 'GOOGLE_DOCS_TOKEN_FILE': str(tmp_path / 'absent.json'),
        'GOOGLE_DOCS_SERVICE_ACCOUNT_FILE': str(tmp_path / 'absent-service.json'),
    })
    async def check():
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                initialized = await session.initialize()
                assert initialized.serverInfo.name == 'google-docs'
                listed = await session.list_tools()
                assert len(listed.tools) == 7
                cases = [
                    ('docs_create', {'title': 'Offline preview'}),
                    ('docs_batch', {'document_id': 'abc', 'requests': [{'insertText': {'text': 'T', 'location': {'index': 1}}}]}),
                    ('docs_insert', {'document_id': 'abc', 'text': 'T', 'tab_id': 'tab'}),
                    ('docs_replace', {'document_id': 'abc', 'text': 'T', 'replacement': 'U', 'tab_id': 'tab'}),
                ]
                for name, arguments in cases:
                    result = await session.call_tool(name, arguments)
                    assert not result.isError
                    assert result.structuredContent['status'] == 'preview'
                invalid = await session.call_tool('docs_create', {'title': 'T', 'confirm': 'true'})
                assert invalid.isError
    asyncio.run(asyncio.wait_for(check(), timeout=30))
    assert not network_attempt.exists(), 'Preview attempted a socket connection'
