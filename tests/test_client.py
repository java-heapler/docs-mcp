import json
from unittest.mock import Mock

import pytest
from googleapiclient.errors import HttpError
from httplib2 import Response

from docs_mcp.client import DocsClient, DocsError


@pytest.fixture
def service():
    service = Mock()
    for method in ('get', 'create', 'batchUpdate'):
        getattr(service.documents.return_value, method).return_value.execute.return_value = {'documentId': 'doc'}
    return service


def test_read_and_apply(service):
    client = DocsClient(service)
    assert client.get_document('doc') == {'documentId': 'doc'}
    service.documents().get.assert_called_once_with(documentId='doc', includeTabsContent=True)
    service.documents().get().execute.assert_called_once_with(num_retries=0)
    assert client.create_document('Title', confirm=True) == {'status': 'applied', 'result': {'documentId': 'doc'}}
    client.batch_update('doc', [{'insertText': {'text': 'a'}}], required_revision_id='opaque/rev=', confirm=True)
    service.documents().batchUpdate.assert_called_once_with(documentId='doc', body={'requests': [{'insertText': {'text': 'a'}}], 'writeControl': {'requiredRevisionId': 'opaque/rev='}})


def test_previews_do_not_initialize_auth(monkeypatch):
    monkeypatch.setattr('docs_mcp.auth.build_service', Mock(side_effect=AssertionError('network')))
    client = DocsClient()
    assert client.create_document('Title') == {'status': 'preview', 'method': 'documents.create', 'body': {'title': 'Title'}}
    result = client.insert_text('doc', '😀\n', 't.abc', index=3, required_revision_id='rev')
    assert result == {'status': 'preview', 'method': 'documents.batchUpdate', 'documentId': 'doc', 'body': {'requests': [{'insertText': {'text': '😀\n', 'location': {'index': 3, 'tabId': 't.abc'}}}], 'writeControl': {'requiredRevisionId': 'rev'}}}
    assert client.replace_text('doc', 'old', '', 't.abc', match_case=False)['body'] == {'requests': [{'replaceAllText': {'containsText': {'text': 'old', 'matchCase': False}, 'replaceText': '', 'tabsCriteria': {'tabIds': ['t.abc']}}}]}
    assert client._service is None


def paragraph(text):
    return {'paragraph': {'elements': [{'textRun': {'content': text}}, {'inlineObjectElement': {}}]}}


def test_recursive_tabs_tables_toc(service):
    table = {'table': {'tableRows': [{'tableCells': [{'content': [paragraph('cell\n'), {'table': {'tableRows': []}}]}]}]}}
    child = {'tabProperties': {'tabId': 't.child', 'title': 'Child'}, 'documentTab': {'body': {'content': [{'tableOfContents': {'content': [paragraph('toc\n')]}}]}}, 'childTabs': [{}]}
    root = {'tabProperties': {'tabId': 't.root', 'title': 'Root'}, 'documentTab': {'body': {'content': [{'sectionBreak': {}}, paragraph('A😀\n'), table]}, 'headers': {'ignore': {}}}, 'childTabs': [child]}
    service.documents().get().execute.return_value = {'documentId': 'doc', 'title': 'Title', 'revisionId': 'rev', 'body': {'content': [paragraph('DUPLICATE')]}, 'tabs': [root]}
    assert DocsClient(service).read_text('doc') == {'documentId': 'doc', 'title': 'Title', 'revisionId': 'rev', 'tabs': [{'tabId': 't.root', 'title': 'Root', 'text': 'A😀\ncell\n'}, {'tabId': 't.child', 'title': 'Child', 'text': 'toc\n'}, {'tabId': None, 'title': '', 'text': ''}]}


def test_legacy_and_empty(service):
    service.documents().get().execute.return_value = {'body': {'content': [paragraph('legacy\n')]}}
    assert DocsClient(service).read_text('doc') == {'documentId': 'doc', 'title': '', 'revisionId': None, 'tabs': [{'tabId': None, 'title': '', 'text': 'legacy\n'}]}
    service.documents().get().execute.return_value = {}
    assert DocsClient(service).read_text('doc')['tabs'][0]['text'] == ''


@pytest.mark.parametrize('bad', ['', 'https://docs.google.com/document/d/id', None, 1, 'a b'])
def test_invalid_document_id(bad):
    with pytest.raises(DocsError):
        DocsClient().get_document(bad)


@pytest.mark.parametrize('call', [
    lambda c: c.create_document(''), lambda c: c.create_document(None),
    lambda c: c.create_document('a\x00'), lambda c: c.create_document('   '),
    lambda c: c.create_document('x', confirm=1),
    lambda c: c.insert_text('doc', '', 't.a'), lambda c: c.insert_text('doc', 1, 't.a'),
    lambda c: c.insert_text('doc', 'x', ''), lambda c: c.insert_text('doc', 'x', 'https://x'),
    lambda c: c.insert_text('doc', 'x', 't.a', index=True), lambda c: c.insert_text('doc', 'x', 't.a', index=0),
    lambda c: c.insert_text('doc', 'x', 't.a', index=1.5),
    lambda c: c.replace_text('doc', '', 'x', 't.a'), lambda c: c.replace_text('doc', 'x', None, 't.a'),
    lambda c: c.replace_text('doc', 'x', 'y', 't.a', match_case=1),
    lambda c: c.batch_update('doc', [{'x': {}}], required_revision_id=''),
])
def test_validation(call):
    with pytest.raises(DocsError):
        call(DocsClient())


@pytest.mark.parametrize('requests', [None, [], {}, [1], [{}], [{'x': {}, 'y': {}}], [{'': {}}], [{1: {}}], [{'x': float('nan')}], [{'x': float('inf')}], [{'x': object()}], [{'x': (1, 2)}], [{'x': {1: 'value'}}]])
def test_invalid_batches(requests):
    with pytest.raises(DocsError):
        DocsClient().batch_update('doc', requests)


def test_json_nested_and_cycle():
    payload = [{'futureOperation': {'nested': [None, True, 1, 2.5, 'str', {}]}}]
    assert json.loads(json.dumps(DocsClient().batch_update('doc', payload)))['body']['requests'] == payload
    circular = []
    circular.append(circular)
    with pytest.raises(DocsError):
        DocsClient().batch_update('doc', [{'x': circular}])


def test_lazy_service(monkeypatch, service):
    build = Mock(return_value=service)
    monkeypatch.setattr('docs_mcp.auth.build_service', build)
    client = DocsClient()
    client.get_document('doc')
    client.get_document('doc')
    build.assert_called_once_with()


@pytest.mark.parametrize('status', [400, 401, 403, 404, 429, 500])
@pytest.mark.parametrize('mutation', [False, True])
def test_http_errors_safe_and_no_retry(service, status, mutation):
    method = service.documents().create if mutation else service.documents().get
    method().execute.side_effect = HttpError(Response({'status': status}), b'{"error":{"message":"SECRET"}}', uri='https://secret')
    with pytest.raises(DocsError) as error:
        DocsClient(service).create_document('x', confirm=True) if mutation else DocsClient(service).get_document('doc')
    assert str(status) in str(error.value)
    assert 'SECRET' not in str(error.value) and 'https://secret' not in str(error.value)
    assert ('may have applied' in str(error.value)) == mutation
    method().execute.assert_called_once_with(num_retries=0)


@pytest.mark.parametrize('mutation', [False, True])
def test_transport_error(service, mutation):
    service.documents.side_effect = OSError('SECRET')
    with pytest.raises(DocsError) as error:
        DocsClient(service).create_document('x', confirm=True) if mutation else DocsClient(service).get_document('doc')
    assert 'SECRET' not in str(error.value)
    assert ('may have applied' in str(error.value)) == mutation


def test_safe_auth_error(monkeypatch):
    monkeypatch.setattr('docs_mcp.auth.build_service', Mock(side_effect=DocsError('Login required')))
    with pytest.raises(DocsError, match='Login required'):
        DocsClient().get_document('doc')
