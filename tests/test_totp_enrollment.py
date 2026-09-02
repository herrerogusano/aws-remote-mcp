"""Security and protocol tests for the loopback TOTP enrollment helper."""

from __future__ import annotations

import importlib.util
import sys
import urllib.parse
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

SCRIPT = Path(__file__).parents[1] / "scripts" / "enroll_cognito_totp.py"


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("enroll_cognito_totp", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_authorization_url_is_pkce_loopback_and_scope_isolated() -> None:
    module = load_script()
    session = module.EnrollmentSession.create(
        "https://auth.example.com", "public-client", "eu-west-1", 6276
    )

    url = urllib.parse.urlsplit(session.authorization_url())
    query = urllib.parse.parse_qs(url.query)

    assert f"{url.scheme}://{url.netloc}" == "https://auth.example.com"
    assert query["response_type"] == ["code"]
    assert query["redirect_uri"] == ["http://127.0.0.1:6276/oauth/callback"]
    assert query["scope"] == ["aws.cognito.signin.user.admin"]
    assert query["code_challenge_method"] == ["S256"]
    assert query["prompt"] == ["login"]
    assert "resource" not in query


def test_begin_validates_state_before_network(monkeypatch: pytest.MonkeyPatch) -> None:
    module = load_script()
    session = module.EnrollmentSession.create(
        "https://auth.example.com", "public-client", "eu-west-1", 6276
    )
    called = False

    def unexpected_post(*_args: object, **_kwargs: object) -> dict[str, Any]:
        nonlocal called
        called = True
        return {}

    monkeypatch.setattr(module, "post_form", unexpected_post)

    with pytest.raises(module.EnrollmentError, match="state validation failed"):
        session.begin("code", "wrong-state")

    assert called is False


def test_verify_uses_token_then_clears_sensitive_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_script()
    session = module.EnrollmentSession.create(
        "https://auth.example.com", "public-client", "eu-west-1", 6276
    )
    session.access_token = "access-token"
    session.secret_code = "SECRET"
    operations: list[tuple[str, dict[str, Any]]] = []

    def fake_post(
        _region: str, operation: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        operations.append((operation, payload))
        return {"Status": "SUCCESS"} if operation == "VerifySoftwareToken" else {}

    monkeypatch.setattr(module, "post_cognito", fake_post)

    session.verify("123456", session.form_token)

    assert [operation for operation, _ in operations] == [
        "VerifySoftwareToken",
        "SetUserMFAPreference",
    ]
    assert session.completed is True
    assert session.access_token is None
    assert session.secret_code is None
    assert session.form_token == ""


def test_helper_has_no_secret_persistence_or_non_loopback_listener() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert 'LOOPBACK_HOST = "127.0.0.1"' in source
    assert "0.0.0.0" not in source
    assert "SecretCode" not in source.split("def main()", maxsplit=1)[1]
    assert "Path(" not in source
    assert "write_text" not in source
    assert "write_bytes" not in source
    assert "log_message" in source
    assert 'Cache-Control", "no-store' in source
    assert "HTTPServer(" in source
    assert "ThreadingHTTPServer" not in source
    assert "amazoncognito.com" in source
    assert 'X-Frame-Options", "DENY"' in source
    assert "application/x-www-form-urlencoded" in source


@pytest.mark.parametrize("code", ["12345", "1234567", "abcdef", "12 345"])
def test_invalid_totp_codes_never_reach_cognito(
    monkeypatch: pytest.MonkeyPatch, code: str
) -> None:
    module = load_script()
    session = module.EnrollmentSession.create(
        "https://auth.example.com", "public-client", "eu-west-1", 6276
    )
    session.access_token = "access-token"
    session.secret_code = "SECRET"

    def unexpected_post(*_args: object, **_kwargs: object) -> dict[str, Any]:
        raise AssertionError("Cognito must not be called")

    monkeypatch.setattr(module, "post_cognito", unexpected_post)

    with pytest.raises(module.EnrollmentError, match="six-digit"):
        session.verify(code, session.form_token)


def test_wrong_local_form_token_never_reaches_cognito(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_script()
    session = module.EnrollmentSession.create(
        "https://auth.example.com", "public-client", "eu-west-1", 6276
    )
    session.access_token = "access-token"
    session.secret_code = "SECRET"

    def unexpected_post(*_args: object, **_kwargs: object) -> dict[str, Any]:
        raise AssertionError("Cognito must not be called")

    monkeypatch.setattr(module, "post_cognito", unexpected_post)

    with pytest.raises(module.EnrollmentError, match="form validation failed"):
        session.verify("123456", "wrong-token")


@pytest.mark.parametrize(
    ("host", "origin"),
    [
        ("127.0.0.1:6276", "http://127.0.0.1:6276"),
        ("127.0.0.1:6276", None),
        ("127.0.0.1:6276", "null"),
        ("localhost:6276", "http://localhost:6276"),
    ],
)
def test_local_browser_origin_variants_are_supported(
    host: str, origin: str | None
) -> None:
    module = load_script()

    assert module.valid_local_request(host, origin, 6276) is True


@pytest.mark.parametrize(
    ("host", "origin"),
    [
        ("attacker.example", "http://127.0.0.1:6276"),
        ("127.0.0.1:6276", "https://attacker.example"),
        ("127.0.0.1:9999", "http://127.0.0.1:9999"),
    ],
)
def test_non_loopback_or_wrong_port_requests_are_rejected(
    host: str, origin: str | None
) -> None:
    module = load_script()

    assert module.valid_local_request(host, origin, 6276) is False


def test_verification_attempts_are_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    module = load_script()
    session = module.EnrollmentSession.create(
        "https://auth.example.com", "public-client", "eu-west-1", 6276
    )
    session.access_token = "access-token"
    session.secret_code = "SECRET"
    calls = 0

    def rejected_post(
        _region: str, operation: str, _payload: dict[str, Any]
    ) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        if operation == "VerifySoftwareToken":
            return {"Status": "ERROR"}
        return {}

    monkeypatch.setattr(module, "post_cognito", rejected_post)

    for _ in range(module.MAX_VERIFY_ATTEMPTS):
        with pytest.raises(module.EnrollmentError, match="didn't verify"):
            session.verify("123456", session.form_token)
    with pytest.raises(module.EnrollmentError, match="attempt limit"):
        session.verify("123456", session.form_token)

    assert calls == module.MAX_VERIFY_ATTEMPTS
