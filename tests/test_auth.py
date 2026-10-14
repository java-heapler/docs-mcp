import json
import os
from unittest.mock import MagicMock
import pytest
from docs_mcp import auth
from docs_mcp.client import DocsError

@pytest.fixture(autouse=True)
def isolated(monkeypatch,tmp_path):
    for name in ('GOOGLE_DOCS_SERVICE_ACCOUNT_FILE','GOOGLE_DOCS_CLIENT_SECRET_FILE'):
        monkeypatch.delenv(name,raising=False)
    monkeypatch.setenv('GOOGLE_DOCS_TOKEN_FILE',str(tmp_path/'token.json'))

def test_doctor_no_network():
    assert auth.doctor()['authenticated'] is False
    with pytest.raises(DocsError,match='auth login'): auth.build_service()

def test_secure_save(tmp_path):
    p=tmp_path/'nested'/'token.json'
    auth._save_token(p,'{"token":"secret"}')
    assert p.stat().st_mode & 0o777 == 0o600
    assert json.loads(p.read_text())['token']=='secret'

def test_symlink_rejected(tmp_path):
    target=tmp_path/'target'; target.write_text('keep')
    p=tmp_path/'token'; p.symlink_to(target)
    with pytest.raises(DocsError): auth._save_token(p,'secret')
    assert target.read_text()=='keep'

def test_login(monkeypatch,tmp_path):
    flow=MagicMock(); flow.run_local_server.return_value.granted_scopes=None; flow.run_local_server.return_value.to_json.return_value='{}'
    factory=MagicMock(return_value=flow)
    monkeypatch.setattr(auth.InstalledAppFlow,'from_client_secrets_file',factory)
    assert auth.login('client.json')['status']=='authenticated'
    assert factory.call_args.kwargs['autogenerate_code_verifier'] is True
    assert flow.run_local_server.call_args.kwargs['host']=='127.0.0.1'
    assert flow.run_local_server.call_args.kwargs['authorization_prompt_message']==''

def test_login_safe_failure(monkeypatch):
    monkeypatch.setattr(auth.InstalledAppFlow,'from_client_secrets_file',MagicMock(side_effect=ValueError('secret')))
    with pytest.raises(DocsError) as e: auth.login('client.json')
    assert 'secret' not in str(e.value)

def test_build_oauth(monkeypatch,tmp_path):
    p=tmp_path/'token.json'; p.write_text('{}'); p.chmod(0o600)
    creds=MagicMock(valid=True,expired=False,granted_scopes=None)
    monkeypatch.setattr(auth.Credentials,'from_authorized_user_file',MagicMock(return_value=creds))
    build=MagicMock(); monkeypatch.setattr(auth,'build',build)
    auth.build_service()
    assert build.call_args.kwargs['num_retries']==0
    assert build.call_args.kwargs['http'].http.timeout==30
    assert build.call_args.kwargs['http']._max_refresh_attempts==0

def test_service_account(monkeypatch,tmp_path):
    monkeypatch.setenv('GOOGLE_DOCS_SERVICE_ACCOUNT_FILE',str(tmp_path/'sa.json'))
    factory=MagicMock(return_value=MagicMock(granted_scopes=None))
    monkeypatch.setattr(auth.service_account.Credentials,'from_service_account_file',factory)
    monkeypatch.setattr(auth,'build',MagicMock())
    auth.build_service(); factory.assert_called_once()

def test_permissions(monkeypatch,tmp_path):
    p=tmp_path/'token.json'; p.write_text('{}'); p.chmod(0o644)
    with pytest.raises(DocsError,match='0600'): auth.build_service()
    assert auth.doctor()['credential_file_private'] is False

@pytest.mark.parametrize('refresh_token', ['token', None])
def test_refresh(monkeypatch,tmp_path,refresh_token):
    p=tmp_path/'token.json'; p.write_text('{}'); p.chmod(0o600)
    creds=MagicMock(valid=False,refresh_token=refresh_token,granted_scopes=None)
    creds.to_json.return_value='{}'
    monkeypatch.setattr(auth.Credentials,'from_authorized_user_file',MagicMock(return_value=creds))
    monkeypatch.setattr(auth,'build',MagicMock())
    if refresh_token:
        auth.build_service()
        assert creds.refresh.call_args.args[0].http.timeout==30
    else:
        with pytest.raises(DocsError,match='renewal'): auth.build_service()

def test_bad_credentials(monkeypatch,tmp_path):
    monkeypatch.setenv('GOOGLE_DOCS_SERVICE_ACCOUNT_FILE',str(tmp_path/'missing'))
    with pytest.raises(DocsError,match='authentication failed'): auth.build_service()

def test_repository_token_rejected(tmp_path):
    (tmp_path/'.git').mkdir()
    with pytest.raises(DocsError,match='outside source'): auth.login('client',str(tmp_path/'token.json'))

def test_login_save_error(monkeypatch):
    flow=MagicMock(); flow.run_local_server.return_value.granted_scopes=None
    monkeypatch.setattr(auth.InstalledAppFlow,'from_client_secrets_file',MagicMock(return_value=flow))
    monkeypatch.setattr(auth,'_save_token',MagicMock(side_effect=DocsError('safe')))
    with pytest.raises(DocsError,match='safe'): auth.login('client')

def test_login_token_timeout(monkeypatch):
    fetch=MagicMock(return_value={'token':'secret'})
    monkeypatch.setattr(auth.InstalledAppFlow,'fetch_token',fetch)
    assert auth._TimedFlow.fetch_token(object.__new__(auth._TimedFlow),code='fake')=={'token':'secret'}
    assert fetch.call_args.kwargs['timeout']==30

def test_save_cleanup_on_failure(monkeypatch,tmp_path):
    monkeypatch.setattr(auth.os,'replace',MagicMock(side_effect=OSError('failed')))
    with pytest.raises(OSError): auth._save_token(tmp_path/'token','{}')
    assert list(tmp_path.iterdir())==[]


@pytest.mark.parametrize('scopes', [None, [], ['https://www.googleapis.com/auth/spreadsheets']])
def test_saved_scopes_must_authorize_docs(tmp_path, scopes):
    """Passing desired scopes to Google's loader must never invent authorization."""
    p=tmp_path/'token.json'
    p.write_text(json.dumps({'token':'fake','refresh_token':'fake','client_id':'fake','client_secret':'fake','scopes':scopes}))
    p.chmod(0o600)
    with pytest.raises(DocsError, match='scope'):
        auth.build_service()


def test_scopes_loaded_without_override(monkeypatch,tmp_path):
    p=tmp_path/'token.json'; p.write_text('{}'); p.chmod(0o600)
    factory=MagicMock(return_value=MagicMock(valid=True,granted_scopes=None))
    monkeypatch.setattr(auth.Credentials,'from_authorized_user_file',factory)
    monkeypatch.setattr(auth,'build',MagicMock())
    auth.build_service()
    factory.assert_called_once_with(str(p))


@pytest.mark.parametrize('granted', [[], ['https://www.googleapis.com/auth/spreadsheets']])
def test_partial_consent_is_rejected(monkeypatch,granted):
    flow=MagicMock(); flow.run_local_server.return_value.granted_scopes=granted
    monkeypatch.setattr(auth.InstalledAppFlow,'from_client_secrets_file',MagicMock(return_value=flow))
    with pytest.raises(DocsError,match='scope'): auth.login('client')


def test_default_path(monkeypatch):
    monkeypatch.delenv('GOOGLE_DOCS_TOKEN_FILE')
    assert auth._token_path() == auth.Path('~/.config/docs-mcp/token.json').expanduser().absolute()


def test_package_root_rejected():
    with pytest.raises(DocsError,match='outside source'):
        auth._check_token_path(auth.Path(auth.__file__).resolve().parents[2]/'token.json')


def test_doctor_private_file_and_service_account(monkeypatch,tmp_path):
    p=tmp_path/'sa'; p.write_text('{}'); p.chmod(0o600)
    monkeypatch.setenv('GOOGLE_DOCS_SERVICE_ACCOUNT_FILE',str(p))
    report=auth.doctor()
    assert report['credential_file_private'] is True
    assert report['auth_mode']=='service_account'
    assert report['authenticated'] is False
    assert report['network_checked'] is False


def test_save_mkstemp_failure(monkeypatch,tmp_path):
    monkeypatch.setattr(auth.tempfile,'mkstemp',MagicMock(side_effect=OSError('failed')))
    with pytest.raises(OSError): auth._save_token(tmp_path/'token','{}')


def test_saved_docs_scopes_create_real_service(tmp_path):
    p=tmp_path/'token.json'
    p.write_text(json.dumps({'token':'fake','refresh_token':'fake','client_id':'fake','client_secret':'fake','scopes':auth.SCOPES,'expiry':'2100-01-01T00:00:00Z'}))
    p.chmod(0o600)
    service=auth.build_service()
    try:
        assert service._http.credentials.scopes == auth.SCOPES
    finally:
        service.close()


def test_granted_docs_scope_is_accepted():
    auth._check_scopes(MagicMock(granted_scopes=auth.SCOPES))


def test_doctor_symlink_is_not_private(tmp_path):
    target=tmp_path/'target'; target.write_text('{}'); target.chmod(0o600)
    (tmp_path/'token.json').symlink_to(target)
    report=auth.doctor()
    assert report['credential_file_present'] is True
    assert report['credential_file_private'] is False


def test_login_retains_explicit_token_timeout(monkeypatch):
    fetch=MagicMock(return_value={})
    monkeypatch.setattr(auth.InstalledAppFlow,'fetch_token',fetch)
    auth._TimedFlow.fetch_token(object.__new__(auth._TimedFlow),timeout=7)
    assert fetch.call_args.kwargs['timeout']==7


def test_installed_package_allows_neighboring_private_credentials(monkeypatch,tmp_path):
    installed=tmp_path/'site-packages'/'docs_mcp'/'auth.py'
    monkeypatch.setattr(auth,'__file__',str(installed))
    token=tmp_path/'private'/'token.json'
    auth._save_token(token,'{}')
    assert token.read_text()=='{}'
    assert token.stat().st_mode & 0o777 == 0o600


def test_unpacked_source_rejects_credentials_without_git(monkeypatch,tmp_path):
    source=tmp_path/'source'
    source.mkdir()
    (source/'pyproject.toml').write_text('[project]\nname="docs-mcp"\n')
    monkeypatch.setattr(auth,'__file__',str(source/'src'/'docs_mcp'/'auth.py'))
    with pytest.raises(DocsError,match='outside source'):
        auth._check_token_path(source/'token.json')
    auth._check_token_path(tmp_path/'private'/'token.json')
