"""Tests for the login CLI module."""

from __future__ import annotations

import io
import json
import http.server
from unittest import mock

import pytest

import login


# ---------------------------------------------------------------------------
# Credential storage
# ---------------------------------------------------------------------------

@mock.patch("login.keyring")
def test_store_and_retrieve_credentials(mock_kr):
    store = {}
    mock_kr.set_password.side_effect = lambda svc, key, val: store.__setitem__((svc, key), val)
    mock_kr.get_password.side_effect = lambda svc, key: store.get((svc, key))

    login.store_credentials("rt_abc", "a@b.com")
    assert login.get_stored_refresh_token() == "rt_abc"
    assert login.get_stored_email() == "a@b.com"


@mock.patch("login.keyring")
def test_get_stored_token_returns_none_when_empty(mock_kr):
    mock_kr.get_password.return_value = None
    assert login.get_stored_refresh_token() is None


@mock.patch("login.keyring")
def test_clear_credentials(mock_kr):
    login.clear_credentials()
    assert mock_kr.delete_password.call_count == 2


@mock.patch("login.keyring")
def test_clear_credentials_ignores_missing(mock_kr):
    mock_kr.errors.PasswordDeleteError = Exception
    mock_kr.delete_password.side_effect = Exception("not found")
    login.clear_credentials()  # should not raise


# ---------------------------------------------------------------------------
# get_id_token
# ---------------------------------------------------------------------------

@mock.patch("login.keyring")
def test_get_id_token_not_logged_in(mock_kr):
    mock_kr.get_password.return_value = None
    with pytest.raises(SystemExit):
        login.get_id_token()


@mock.patch("login.keyring")
@mock.patch("login.urllib.request.urlopen")
def test_get_id_token_success(mock_urlopen, mock_kr):
    mock_kr.get_password.side_effect = lambda svc, key: "rt_old" if "token" in key else None

    resp_body = json.dumps({"id_token": "id_123", "refresh_token": "rt_old"}).encode()
    mock_resp = mock.MagicMock()
    mock_resp.read.return_value = resp_body
    mock_resp.__enter__ = mock.Mock(return_value=mock_resp)
    mock_resp.__exit__ = mock.Mock(return_value=False)
    mock_urlopen.return_value = mock_resp

    assert login.get_id_token() == "id_123"
    # No rotation — same refresh token, so set_password not called
    mock_kr.set_password.assert_not_called()


@mock.patch("login.keyring")
@mock.patch("login.urllib.request.urlopen")
def test_get_id_token_rotates_refresh_token(mock_urlopen, mock_kr):
    mock_kr.get_password.side_effect = lambda svc, key: "rt_old" if "token" in key else None

    resp_body = json.dumps({"id_token": "id_456", "refresh_token": "rt_new"}).encode()
    mock_resp = mock.MagicMock()
    mock_resp.read.return_value = resp_body
    mock_resp.__enter__ = mock.Mock(return_value=mock_resp)
    mock_resp.__exit__ = mock.Mock(return_value=False)
    mock_urlopen.return_value = mock_resp

    assert login.get_id_token() == "id_456"
    mock_kr.set_password.assert_called_once_with(
        login.KEYRING_SERVICE, login.KEYRING_KEY_TOKEN, "rt_new",
    )


@mock.patch("login.keyring")
@mock.patch("login.urllib.request.urlopen")
def test_get_id_token_http_error(mock_urlopen, mock_kr):
    mock_kr.get_password.side_effect = lambda svc, key: "rt_old" if "token" in key else None
    mock_urlopen.side_effect = login.urllib.error.HTTPError(
        url="", code=400, msg="Bad Request", hdrs={}, fp=io.BytesIO(b"bad"),
    )
    with pytest.raises(SystemExit):
        login.get_id_token()


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------

def test_handler_serves_login_page():
    handler = _make_handler("GET", "/login")
    handler.do_GET()
    assert handler._response_code == 200
    assert b"Sign in with Google" in handler._response_body


def test_handler_redirects_root():
    handler = _make_handler("GET", "/")
    handler.do_GET()
    assert handler._response_code == 302


def test_handler_receives_callback():
    payload = json.dumps({"refresh_token": "rt", "email": "u@x.com"}).encode()
    handler = _make_handler("POST", "/callback", body=payload)
    handler.do_POST()
    assert handler._response_code == 200
    assert handler.server.oauth_result == {"refresh_token": "rt", "email": "u@x.com"}


# ---------------------------------------------------------------------------
# CLI subcommands
# ---------------------------------------------------------------------------

@mock.patch("login.keyring")
def test_cli_whoami_not_logged_in(mock_kr):
    mock_kr.get_password.return_value = None
    with pytest.raises(SystemExit):
        login.main(["whoami"])


@mock.patch("login.keyring")
def test_cli_whoami_logged_in(mock_kr, capsys):
    mock_kr.get_password.side_effect = lambda svc, key: "a@b.com" if "email" in key else "rt"
    login.main(["whoami"])
    assert "a@b.com" in capsys.readouterr().out


@mock.patch("login.keyring")
def test_cli_logout(mock_kr):
    mock_kr.errors.PasswordDeleteError = Exception
    login.main(["logout"])
    assert mock_kr.delete_password.call_count == 2


@mock.patch("login.get_id_token", return_value="tok_xyz")
def test_cli_token(mock_tok, capsys):
    login.main(["token"])
    assert "tok_xyz" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _FakeServer:
    oauth_result = None


def _make_handler(method: str, path: str, body: bytes = b""):
    """Create an _OAuthCallbackHandler without a real socket."""
    handler = login._OAuthCallbackHandler.__new__(login._OAuthCallbackHandler)
    handler.server = _FakeServer()
    handler.path = path
    handler.headers = {"Content-Length": str(len(body))}
    handler.rfile = io.BytesIO(body)
    handler.wfile = io.BytesIO()
    handler._response_code = None
    handler._response_body = b""
    handler._response_headers = {}

    def send_response(code):
        handler._response_code = code
    def send_header(k, v):
        handler._response_headers[k] = v
    def end_headers():
        pass

    handler.send_response = send_response
    handler.send_header = send_header
    handler.end_headers = end_headers

    original_write = handler.wfile.write
    def capturing_write(data):
        handler._response_body += data
        return original_write(data)
    handler.wfile.write = capturing_write

    return handler
