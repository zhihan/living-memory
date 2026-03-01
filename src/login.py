"""CLI login command — browser-based Google OAuth via Firebase."""

from __future__ import annotations

import argparse
import http.server
import json
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
import webbrowser

try:
    import keyring
except ImportError:
    keyring = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Firebase config (must match client/index.html)
# ---------------------------------------------------------------------------
FIREBASE_API_KEY = "AIzaSyCRPmK9euOr_rDVcQDBh_BC9OVM2MnJF0s"
FIREBASE_AUTH_DOMAIN = "living-memories-488001.firebaseapp.com"
FIREBASE_PROJECT_ID = "living-memories-488001"

KEYRING_SERVICE = "living-memory-cli"
KEYRING_KEY_TOKEN = "refresh_token"
KEYRING_KEY_EMAIL = "email"

# ---------------------------------------------------------------------------
# Token storage helpers
# ---------------------------------------------------------------------------

def _require_keyring():
    if keyring is None:
        print("Error: 'keyring' package is required. Install with: pip install keyring", file=sys.stderr)
        sys.exit(1)


def store_credentials(refresh_token: str, email: str) -> None:
    _require_keyring()
    keyring.set_password(KEYRING_SERVICE, KEYRING_KEY_TOKEN, refresh_token)
    keyring.set_password(KEYRING_SERVICE, KEYRING_KEY_EMAIL, email)


def get_stored_refresh_token() -> str | None:
    _require_keyring()
    return keyring.get_password(KEYRING_SERVICE, KEYRING_KEY_TOKEN)


def get_stored_email() -> str | None:
    _require_keyring()
    return keyring.get_password(KEYRING_SERVICE, KEYRING_KEY_EMAIL)


def clear_credentials() -> None:
    _require_keyring()
    for key in (KEYRING_KEY_TOKEN, KEYRING_KEY_EMAIL):
        try:
            keyring.delete_password(KEYRING_SERVICE, key)
        except keyring.errors.PasswordDeleteError:
            pass


# ---------------------------------------------------------------------------
# Exchange refresh token for a fresh ID token
# ---------------------------------------------------------------------------

def get_id_token() -> str:
    """Return a fresh Firebase ID token, or exit with an error."""
    _require_keyring()
    refresh_token = get_stored_refresh_token()
    if not refresh_token:
        print("Not logged in. Run: login", file=sys.stderr)
        sys.exit(1)

    url = f"https://securetoken.googleapis.com/v1/token?key={FIREBASE_API_KEY}"
    data = urllib.parse.urlencode({
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }).encode()

    try:
        req = urllib.request.Request(url, data=data)
        with urllib.request.urlopen(req) as resp:
            body = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        print(f"Token refresh failed (HTTP {exc.code}): {exc.read().decode()}", file=sys.stderr)
        sys.exit(1)

    # If the server rotated the refresh token, persist the new one.
    new_refresh = body.get("refresh_token")
    if new_refresh and new_refresh != refresh_token:
        keyring.set_password(KEYRING_SERVICE, KEYRING_KEY_TOKEN, new_refresh)

    return body["id_token"]


# ---------------------------------------------------------------------------
# Login HTML page served to the browser
# ---------------------------------------------------------------------------

_LOGIN_HTML = """\
<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Living Memory — Sign In</title>
<style>
  body { font-family: system-ui, sans-serif; display: flex; justify-content: center;
         align-items: center; min-height: 100vh; margin: 0; background: #f5f5f5; }
  .card { background: white; padding: 2rem; border-radius: 8px;
          box-shadow: 0 2px 8px rgba(0,0,0,.1); text-align: center; max-width: 400px; }
  button { padding: .75rem 1.5rem; font-size: 1rem; cursor: pointer;
           border: 1px solid #ccc; border-radius: 4px; background: white; }
  button:hover { background: #f0f0f0; }
  #status { margin-top: 1rem; color: #666; }
</style></head><body>
<div class="card">
  <h2>Living Memory CLI</h2>
  <p>Sign in with your Google account to continue.</p>
  <button id="signin">Sign in with Google</button>
  <div id="status"></div>
</div>
<script type="module">
import { initializeApp } from "https://www.gstatic.com/firebasejs/11.4.0/firebase-app.js";
import { getAuth, signInWithPopup, GoogleAuthProvider }
  from "https://www.gstatic.com/firebasejs/11.4.0/firebase-auth.js";

const app = initializeApp({
  apiKey: "%(api_key)s",
  authDomain: "%(auth_domain)s",
  projectId: "%(project_id)s",
});
const auth = getAuth(app);
const status = document.getElementById("status");

document.getElementById("signin").addEventListener("click", async () => {
  status.textContent = "Opening sign-in popup…";
  try {
    const result = await signInWithPopup(auth, new GoogleAuthProvider());
    const refreshToken = result.user.refreshToken;
    const email = result.user.email;
    status.textContent = "Sending credentials to CLI…";
    const resp = await fetch("/callback", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({refresh_token: refreshToken, email: email}),
    });
    if (resp.ok) {
      status.innerHTML = "<strong>Signed in! You can close this tab.</strong>";
      document.getElementById("signin").style.display = "none";
    } else {
      status.textContent = "Error sending credentials to CLI.";
    }
  } catch (err) {
    status.textContent = "Sign-in failed: " + err.message;
  }
});
</script></body></html>
"""


# ---------------------------------------------------------------------------
# Local HTTP server to receive OAuth callback
# ---------------------------------------------------------------------------

class _OAuthCallbackHandler(http.server.BaseHTTPRequestHandler):
    """Serves login page and receives the OAuth callback."""

    def do_GET(self):
        if self.path == "/login":
            html = _LOGIN_HTML % {
                "api_key": FIREBASE_API_KEY,
                "auth_domain": FIREBASE_AUTH_DOMAIN,
                "project_id": FIREBASE_PROJECT_ID,
            }
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(html.encode())
        else:
            self.send_response(302)
            self.send_header("Location", "/login")
            self.end_headers()

    def do_POST(self):
        if self.path == "/callback":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            self.server.oauth_result = body  # type: ignore[attr-defined]
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):  # noqa: A002
        pass  # silence request logs


def run_login_flow(timeout: int = 120) -> tuple[str, str]:
    """Start local server, open browser, wait for callback.

    Returns (refresh_token, email).
    """
    server = http.server.HTTPServer(("127.0.0.1", 0), _OAuthCallbackHandler)
    server.oauth_result = None  # type: ignore[attr-defined]
    port = server.server_address[1]

    url = f"http://localhost:{port}/login"
    print(f"Opening browser to {url}")
    webbrowser.open(url)

    server.timeout = timeout
    while server.oauth_result is None:  # type: ignore[attr-defined]
        server.handle_request()

    result = server.oauth_result  # type: ignore[attr-defined]
    server.server_close()
    return result["refresh_token"], result["email"]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="login", description="Authenticate with Living Memory")
    parser.add_argument("command", nargs="?", default="login",
                        choices=["login", "whoami", "logout", "token"],
                        help="Subcommand (default: login)")
    args = parser.parse_args(argv)

    if args.command == "login":
        _require_keyring()
        refresh_token, email = run_login_flow()
        store_credentials(refresh_token, email)
        print(f"Logged in as {email}")

    elif args.command == "whoami":
        email = get_stored_email()
        if email:
            print(email)
        else:
            print("Not logged in.", file=sys.stderr)
            sys.exit(1)

    elif args.command == "logout":
        clear_credentials()
        print("Logged out.")

    elif args.command == "token":
        token = get_id_token()
        print(token)


if __name__ == "__main__":
    main()
