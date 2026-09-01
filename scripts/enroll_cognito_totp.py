"""One-time loopback TOTP enrollment for an administrator-created Cognito user."""

from __future__ import annotations

import argparse
import base64
import hashlib
import html
import json
import re
import secrets
import threading
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Never

LOOPBACK_HOST = "127.0.0.1"
CALLBACK_PATH = "/oauth/callback"
VERIFY_PATH = "/verify"
COGNITO_ADMIN_SCOPE = "aws.cognito.signin.user.admin"
CODE_PATTERN = re.compile(r"^[0-9]{6}$")
MAX_VERIFY_ATTEMPTS = 5


class EnrollmentError(RuntimeError):
    """Safe operational error without tokens or private enrollment data."""


def base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def post_form(url: str, values: dict[str, str]) -> dict[str, Any]:
    body = urllib.parse.urlencode(values).encode("ascii")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    return read_json(request)


def post_cognito(
    region: str, operation: str, payload: dict[str, Any]
) -> dict[str, Any]:
    request = urllib.request.Request(
        f"https://cognito-idp.{region}.amazonaws.com/",
        data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
        headers={
            "Content-Type": "application/x-amz-json-1.1",
            "X-Amz-Target": f"AWSCognitoIdentityProviderService.{operation}",
        },
        method="POST",
    )
    return read_json(request)


def read_json(request: urllib.request.Request) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            value = json.load(response)
    except urllib.error.HTTPError as error:
        try:
            detail = json.load(error)
            error_type = str(detail.get("__type", "CognitoError")).split("#")[-1]
        except (json.JSONDecodeError, AttributeError):
            error_type = "CognitoError"
        raise EnrollmentError(
            f"Cognito rejected the operation: {error_type}"
        ) from error
    except urllib.error.URLError as error:
        raise EnrollmentError("The Cognito endpoint couldn't be reached") from error
    if not isinstance(value, dict):
        raise EnrollmentError("Cognito returned an unexpected response")
    return value


@dataclass
class EnrollmentSession:
    authorization_server: str
    client_id: str
    region: str
    port: int
    verifier: str
    state: str
    form_token: str
    access_token: str | None = None
    secret_code: str | None = None
    verify_attempts: int = 0
    completed: bool = False

    @classmethod
    def create(
        cls, authorization_server: str, client_id: str, region: str, port: int
    ) -> EnrollmentSession:
        return cls(
            authorization_server=authorization_server.rstrip("/"),
            client_id=client_id,
            region=region,
            port=port,
            verifier=base64url(secrets.token_bytes(32)),
            state=base64url(secrets.token_bytes(24)),
            form_token=base64url(secrets.token_bytes(24)),
        )

    @property
    def redirect_uri(self) -> str:
        return f"http://{LOOPBACK_HOST}:{self.port}{CALLBACK_PATH}"

    @property
    def local_origin(self) -> str:
        return f"http://{LOOPBACK_HOST}:{self.port}"

    def authorization_url(self) -> str:
        challenge = base64url(hashlib.sha256(self.verifier.encode("ascii")).digest())
        query = urllib.parse.urlencode(
            {
                "response_type": "code",
                "client_id": self.client_id,
                "redirect_uri": self.redirect_uri,
                "scope": COGNITO_ADMIN_SCOPE,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "state": self.state,
                "prompt": "login",
            }
        )
        return f"{self.authorization_server}/oauth2/authorize?{query}"

    def begin(self, code: str, returned_state: str) -> None:
        if not secrets.compare_digest(returned_state, self.state):
            raise EnrollmentError("The OAuth state validation failed")
        if self.access_token is not None or self.secret_code is not None:
            raise EnrollmentError("The enrollment callback was already used")
        token = post_form(
            f"{self.authorization_server}/oauth2/token",
            {
                "grant_type": "authorization_code",
                "client_id": self.client_id,
                "code": code,
                "redirect_uri": self.redirect_uri,
                "code_verifier": self.verifier,
            },
        ).get("access_token")
        if not isinstance(token, str) or not token:
            raise EnrollmentError("Cognito didn't return an enrollment token")
        setup = post_cognito(
            self.region, "AssociateSoftwareToken", {"AccessToken": token}
        )
        secret_code = setup.get("SecretCode")
        if not isinstance(secret_code, str) or not secret_code:
            raise EnrollmentError("Cognito didn't return a TOTP setup key")
        self.access_token = token
        self.secret_code = secret_code
        self.verifier = ""

    def verify(self, user_code: str, returned_form_token: str) -> None:
        if not secrets.compare_digest(returned_form_token, self.form_token):
            raise EnrollmentError("The local form validation failed")
        if not CODE_PATTERN.fullmatch(user_code):
            raise EnrollmentError("Enter the current six-digit authenticator code")
        if self.access_token is None or self.secret_code is None:
            raise EnrollmentError("The enrollment session isn't ready")
        if self.verify_attempts >= MAX_VERIFY_ATTEMPTS:
            raise EnrollmentError("The local verification attempt limit was reached")
        self.verify_attempts += 1
        result = post_cognito(
            self.region,
            "VerifySoftwareToken",
            {"AccessToken": self.access_token, "UserCode": user_code},
        )
        if result.get("Status") != "SUCCESS":
            raise EnrollmentError("Cognito didn't verify the authenticator code")
        post_cognito(
            self.region,
            "SetUserMFAPreference",
            {
                "AccessToken": self.access_token,
                "SoftwareTokenMfaSettings": {"Enabled": True, "PreferredMfa": True},
            },
        )
        self.completed = True
        self.access_token = None
        self.secret_code = None
        self.form_token = ""


def page(title: str, body: str) -> bytes:
    escaped_title = html.escape(title)
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width">'
        '<meta http-equiv="Content-Security-Policy" '
        "content=\"default-src 'none'; style-src 'unsafe-inline'; "
        "form-action 'self'; base-uri 'none'\">"
        '<meta http-equiv="Cache-Control" content="no-store">'
        f"<title>{escaped_title}</title><style>"
        "body{font:16px system-ui;max-width:42rem;margin:4rem auto;"
        "padding:0 1rem;color:#17202a}code,input{font:1rem ui-monospace,monospace}"
        "code{display:block;padding:1rem;background:#f2f4f4;overflow-wrap:anywhere}"
        "input,button{padding:.7rem;margin-top:1rem}button{cursor:pointer}"
        f"</style></head><body><h1>{escaped_title}</h1>{body}</body></html>"
    ).encode()


def handler_for(session: EnrollmentSession) -> type[BaseHTTPRequestHandler]:
    class EnrollmentHandler(BaseHTTPRequestHandler):
        def log_message(self, _format: str, *_args: object) -> None:
            return

        def send_page(self, status: HTTPStatus, content: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store, max-age=0")
            self.send_header("Pragma", "no-cache")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def do_GET(self) -> None:
            if self.headers.get("Host") != f"{LOOPBACK_HOST}:{session.port}":
                self.send_page(HTTPStatus.BAD_REQUEST, page("Invalid host", ""))
                return
            parsed = urllib.parse.urlsplit(self.path)
            if parsed.path != CALLBACK_PATH:
                self.send_page(HTTPStatus.NOT_FOUND, page("Not found", ""))
                return
            values = urllib.parse.parse_qs(parsed.query, strict_parsing=True)
            try:
                code = single(values, "code")
                returned_state = single(values, "state")
                session.begin(code, returned_state)
                assert session.secret_code is not None
                body = (
                    "<p>Add a time-based account in your authenticator with "
                    "this setup key:</p>"
                    f"<code>{html.escape(session.secret_code)}</code>"
                    f'<form method="post" action="{VERIFY_PATH}">'
                    f'<input type="hidden" name="form_token" '
                    f'value="{html.escape(session.form_token)}">'
                    "<label>Current six-digit code "
                    '<input name="code" inputmode="numeric" '
                    'autocomplete="one-time-code" '
                    'pattern="[0-9]{6}" maxlength="6" required></label><br>'
                    '<button type="submit">Verify TOTP</button></form>'
                )
                self.send_page(HTTPStatus.OK, page("Configure TOTP", body))
            except (EnrollmentError, ValueError, AssertionError) as error:
                self.send_page(
                    HTTPStatus.BAD_REQUEST,
                    page("Enrollment failed", f"<p>{html.escape(str(error))}</p>"),
                )

        def do_POST(self) -> None:
            if (
                self.headers.get("Host") != f"{LOOPBACK_HOST}:{session.port}"
                or self.headers.get("Origin") != session.local_origin
            ):
                self.send_page(HTTPStatus.FORBIDDEN, page("Invalid origin", ""))
                return
            if self.path != VERIFY_PATH:
                self.send_page(HTTPStatus.NOT_FOUND, page("Not found", ""))
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length < 1 or length > 128:
                    raise EnrollmentError("Invalid verification request")
                values = urllib.parse.parse_qs(
                    self.rfile.read(length).decode("ascii"), strict_parsing=True
                )
                session.verify(single(values, "code"), single(values, "form_token"))
                self.send_page(
                    HTTPStatus.OK,
                    page(
                        "TOTP enabled",
                        "<p>The authenticator is active. You can close this tab.</p>",
                    ),
                )
                threading.Thread(target=self.server.shutdown, daemon=True).start()
            except (EnrollmentError, ValueError, UnicodeDecodeError) as error:
                self.send_page(
                    HTTPStatus.BAD_REQUEST,
                    page("Verification failed", f"<p>{html.escape(str(error))}</p>"),
                )

    return EnrollmentHandler


def single(values: dict[str, list[str]], key: str) -> str:
    items = values.get(key, [])
    if len(items) != 1 or not items[0]:
        raise EnrollmentError(f"Missing or repeated {key} parameter")
    return items[0]


def fail(message: str) -> Never:
    raise SystemExit(message)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authorization-server", required=True)
    parser.add_argument("--client-id", required=True)
    parser.add_argument("--region", default="eu-west-1")
    parser.add_argument("--port", type=int, default=6276)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        fail("port must be between 1024 and 65535")
    if not args.authorization_server.startswith("https://"):
        fail("authorization server must use HTTPS")
    session = EnrollmentSession.create(
        args.authorization_server, args.client_id, args.region, args.port
    )
    server = ThreadingHTTPServer(
        (LOOPBACK_HOST, args.port), handler_for(session), bind_and_activate=False
    )
    server.allow_reuse_address = False
    server.server_bind()
    server.server_activate()
    print(f"Listening only on http://{LOOPBACK_HOST}:{args.port}")
    print("No tokens or TOTP secrets are written to disk or terminal output.")
    webbrowser.open(session.authorization_url(), new=1, autoraise=True)
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        print("Enrollment cancelled.")
    finally:
        session.access_token = None
        session.secret_code = None
        server.server_close()
    if session.completed:
        print("TOTP enrollment completed successfully.")


if __name__ == "__main__":
    main()
