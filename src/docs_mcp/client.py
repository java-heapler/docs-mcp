"""Preview-first Google Docs API client; insertion indexes use UTF-16 units."""
import json
import re

from googleapiclient.errors import HttpError


class DocsError(Exception):
    """A sanitized error safe for CLI and MCP output."""


def _identifier(value, label, pattern=r'[A-Za-z0-9_-]+'):
    if not isinstance(value, str) or not re.fullmatch(pattern, value):
        raise DocsError(f'{label} must be an ID, not a URL.')


def _label(value, label):
    if not isinstance(value, str) or not value.strip() or any(ord(c) < 32 for c in value):
        raise DocsError(f'{label} must be nonempty text without control characters.')


def _text(value, label):
    if not isinstance(value, str) or not value:
        raise DocsError(f'{label} must be nonempty text.')


def _json_types(value):
    if isinstance(value, dict):
        return all(isinstance(key, str) and _json_types(item) for key, item in value.items())
    if isinstance(value, list):
        return all(_json_types(item) for item in value)
    return value is None or isinstance(value, (str, bool, int, float))


def _finite_json(value):
    try:
        json.dumps(value, allow_nan=False)
        if not _json_types(value):
            raise ValueError
    except (ValueError, TypeError, OverflowError, RecursionError):
        raise DocsError('Payload must contain finite JSON data with string object keys.') from None


def _body_text(content):
    parts = []
    for element in content:
        if 'paragraph' in element:
            for run in element['paragraph'].get('elements', []):
                parts.append(run.get('textRun', {}).get('content', ''))
        elif 'table' in element:
            for row in element['table'].get('tableRows', []):
                for cell in row.get('tableCells', []):
                    parts.append(_body_text(cell.get('content', [])))
        elif 'tableOfContents' in element:
            parts.append(_body_text(element['tableOfContents'].get('content', [])))
    return ''.join(parts)


def _tabs_text(tabs):
    result = []
    for tab in tabs:
        properties = tab.get('tabProperties', {})
        result.append({'tabId': properties.get('tabId'), 'title': properties.get('title', ''),
                       'text': _body_text(tab.get('documentTab', {}).get('body', {}).get('content', []))})
        result.extend(_tabs_text(tab.get('childTabs', [])))
    return result


class DocsClient:
    def __init__(self, service=None):
        self._service = service

    def _execute(self, method, kwargs, mutation=False):
        try:
            if self._service is None:
                from .auth import build_service
                self._service = build_service()
            result = getattr(self._service.documents(), method)(**kwargs).execute(num_retries=0)
            return {'status': 'applied', 'result': result} if mutation else result
        except DocsError:
            raise
        except HttpError as error:
            status = error.resp.status
            reason = {401: 'Authentication expired; run google-docs auth login.',
                      403: 'Access denied; check sharing, scopes, and Docs API enablement.',
                      404: 'Document not found; check the ID and access.',
                      429: 'Rate limited; wait before another request.'}.get(status, 'Google Docs request failed.')
            if mutation:
                reason += ' The write may have applied; inspect the document before retrying.'
            raise DocsError(f'Google Docs HTTP {status}: {reason}') from None
        except Exception:
            suffix = ' The write may have applied; inspect the document before retrying.' if mutation else ''
            raise DocsError('Google Docs request failed.' + suffix) from None

    def _mutate(self, method, kwargs, confirm):
        if not isinstance(confirm, bool):
            raise DocsError('confirm must be a boolean.')
        if not confirm:
            return {'status': 'preview', 'method': f'documents.{method}', **kwargs}
        return self._execute(method, kwargs, mutation=True)

    def get_document(self, document_id: str):
        _identifier(document_id, 'document_id')
        return self._execute('get', {'documentId': document_id, 'includeTabsContent': True})

    def read_text(self, document_id: str):
        """Extract body text from all tabs, tables and TOCs (not headers/footnotes)."""
        document = self.get_document(document_id)
        tabs = _tabs_text(document.get('tabs', []))
        if not tabs:
            tabs = [{'tabId': None, 'title': '', 'text': _body_text(document.get('body', {}).get('content', []))}]
        return {'documentId': document.get('documentId', document_id), 'title': document.get('title', ''),
                'revisionId': document.get('revisionId'), 'tabs': tabs}

    def create_document(self, title: str, confirm: bool = False):
        _label(title, 'title')
        return self._mutate('create', {'body': {'title': title}}, confirm)

    def batch_update(self, document_id: str, requests: list[dict], required_revision_id: str | None = None, confirm: bool = False):
        _identifier(document_id, 'document_id')
        _finite_json(requests)
        if not isinstance(requests, list) or not requests or any(not isinstance(item, dict) or len(item) != 1 for item in requests):
            raise DocsError('requests must be a nonempty array of single-operation objects.')
        for item in requests:
            _label(next(iter(item)), 'operation')
        body = {'requests': requests}
        if required_revision_id is not None:
            _label(required_revision_id, 'required_revision_id')
            body['writeControl'] = {'requiredRevisionId': required_revision_id}
        return self._mutate('batchUpdate', {'documentId': document_id, 'body': body}, confirm)

    def insert_text(self, document_id: str, text: str, tab_id: str, index: int = 1, required_revision_id: str | None = None, confirm: bool = False):
        """Insert at an API UTF-16 code-unit index, never a Python character offset."""
        _text(text, 'text')
        _identifier(tab_id, 'tab_id', r'[A-Za-z0-9_.-]+')
        if type(index) is not int or index < 1:
            raise DocsError('index must be an integer >= 1 in UTF-16 code units.')
        return self.batch_update(document_id, [{'insertText': {'text': text, 'location': {'index': index, 'tabId': tab_id}}}], required_revision_id, confirm)

    def replace_text(self, document_id: str, text: str, replacement: str, tab_id: str, match_case: bool = True, required_revision_id: str | None = None, confirm: bool = False):
        _text(text, 'text')
        if not isinstance(replacement, str):
            raise DocsError('replacement must be text (empty text deletes matches).')
        _identifier(tab_id, 'tab_id', r'[A-Za-z0-9_.-]+')
        if not isinstance(match_case, bool):
            raise DocsError('match_case must be a boolean.')
        request = {'replaceAllText': {'containsText': {'text': text, 'matchCase': match_case},
                                     'replaceText': replacement, 'tabsCriteria': {'tabIds': [tab_id]}}}
        return self.batch_update(document_id, [request], required_revision_id, confirm)
