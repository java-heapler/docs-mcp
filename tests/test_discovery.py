"""Exercise actual official SDK discovery/serialization without credentials/network."""
import json
from unittest.mock import Mock

from googleapiclient.discovery import build
from httplib2 import Response

from docs_mcp.client import DocsClient


def test_official_discovery_supports_tab_reads_and_writes():
    http = Mock(spec=['request', 'close'])
    http.request.return_value = (Response({'status': 200}), b'{"documentId":"doc"}')
    service = build('docs', 'v1', http=http, static_discovery=True)
    client = DocsClient(service)
    client.get_document('doc')
    assert 'includeTabsContent=true' in http.request.call_args.args[0]
    client.insert_text('doc', '😀\n', 't.example', index=4, required_revision_id='revision', confirm=True)
    args, kwargs = http.request.call_args
    assert args[0] == 'https://docs.googleapis.com/v1/documents/doc:batchUpdate?alt=json'
    assert args[1] == 'POST'
    assert json.loads(kwargs['body']) == {'requests': [{'insertText': {'text': '😀\n', 'location': {'index': 4, 'tabId': 't.example'}}}], 'writeControl': {'requiredRevisionId': 'revision'}}
    client.replace_text('doc', 'a', 'b', 't.example', confirm=True)
    assert json.loads(http.request.call_args.kwargs['body'])['requests'][0]['replaceAllText']['tabsCriteria'] == {'tabIds': ['t.example']}
    client.create_document('Example', confirm=True)
    assert json.loads(http.request.call_args.kwargs['body']) == {'title': 'Example'}
    assert http.request.call_count == 4
    service.close()
