import pytest
from docs_mcp import auth
from unittest.mock import MagicMock

@pytest.mark.parametrize('response_status', [None, 200, 307, 401, 503])
def test_transport_never_replays_post(response_status):
    """A real loopback server records complete POST bodies before losing replies."""
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread
    from google.auth.credentials import AnonymousCredentials
    from googleapiclient.http import HttpRequest
    import requests
    from googleapiclient.errors import HttpError

    received = []
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            received.append(self.rfile.read(int(self.headers['Content-Length'])))
            if response_status is None:
                self.close_connection = True
                return
            self.send_response(response_status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Location', '/redirect-target')
            self.end_headers()
            self.wfile.write(b'{}')
        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = Thread(target=server.serve_forever, kwargs={'poll_interval':0.01}, daemon=True)
    thread.start()
    transport = auth._NoReplayHttp()
    authorized = auth.AuthorizedHttp(AnonymousCredentials(), http=transport, max_refresh_attempts=0)
    request = HttpRequest(authorized, lambda response, body: body,
                          f'http://127.0.0.1:{server.server_port}/sheets',
                          method='POST', body='{"write":true}', headers={'Content-Type':'application/json'})
    try:
        if response_status is None:
            with pytest.raises(requests.exceptions.ConnectionError): request.execute(num_retries=0)
        elif response_status >= 300:
            with pytest.raises(HttpError): request.execute(num_retries=0)
        else:
            assert request.execute(num_retries=0) == b'{}'
        assert received == [b'{"write":true}']
        assert transport.timeout == 30
        assert transport.session.get_adapter('https://').max_retries.total == 0
    finally:
        authorized.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

def test_real_discovery_uses_no_replay_transport(monkeypatch,tmp_path):
    monkeypatch.delenv('GOOGLE_DOCS_SERVICE_ACCOUNT_FILE',raising=False)
    monkeypatch.setenv('GOOGLE_DOCS_TOKEN_FILE',str(tmp_path/'token.json'))
    p=tmp_path/'token.json'; p.write_text('{}'); p.chmod(0o600)
    monkeypatch.setattr(auth.Credentials,'from_authorized_user_file',MagicMock(return_value=auth.Credentials(token='fake',scopes=auth.SCOPES)))
    service=auth.build_service()
    try:
        assert isinstance(service._http.http,auth._NoReplayHttp)
        request=service.documents().batchUpdate(documentId='abc',body={'requests':[{'insertText':{'endOfSegmentLocation':{},'text':'hello'}}]})
        assert request.method=='POST'
        assert request.uri.startswith('https://docs.googleapis.com/v1/documents/abc:batchUpdate')
    finally:
        service.close()
