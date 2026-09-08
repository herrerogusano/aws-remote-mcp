"""Offline contract tests for single-attempt external integrations."""

import json
from typing import Any
from urllib.error import URLError
from urllib.parse import parse_qs
from urllib.request import Request

import pytest

from aws_remote_mcp.adapters.external_integrations import (
    HTTP_TIMEOUT_SECONDS,
    SsmIntegrationConfigProvider,
    SsmTelegramAdapter,
    SsmTrelloAdapter,
    TelegramHttpAdapter,
    TrelloHttpAdapter,
)
from aws_remote_mcp.adapters.protocols import AdapterError

TELEGRAM_TOKEN = "123456789:abcdefghijklmnopqrstuvwxyz_ABCDEFG"
TRELLO_KEY = "trello_api_key_123"
TRELLO_TOKEN = "trello_api_token_456"
TRELLO_LIST_ID = "0123456789abcdef01234567"


class RecordingTransport:
    def __init__(self, status: int, response: bytes) -> None:
        self.status = status
        self.response = response
        self.calls: list[tuple[Request, float]] = []

    def __call__(self, request: Request, timeout: float) -> tuple[int, bytes]:
        self.calls.append((request, timeout))
        return self.status, self.response


class RaisingTransport:
    def __init__(self, error: Exception) -> None:
        self.error = error
        self.calls = 0

    def __call__(self, _request: Request, _timeout: float) -> tuple[int, bytes]:
        self.calls += 1
        raise self.error


class FakeSsmClient:
    def __init__(self, value: str) -> None:
        self.value = value
        self.calls: list[dict[str, Any]] = []

    def get_parameter(self, **request: Any) -> dict[str, Any]:
        self.calls.append(request)
        return {
            "Parameter": {
                "Name": request["Name"],
                "Type": "SecureString",
                "Value": self.value,
            }
        }


class StaticSsmClient:
    def __init__(self, response: dict[str, Any] | Exception) -> None:
        self.response = response
        self.calls = 0

    def get_parameter(self, **_request: Any) -> dict[str, Any]:
        self.calls += 1
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def body_fields(request: Request) -> dict[str, list[str]]:
    assert isinstance(request.data, bytes)
    return parse_qs(request.data.decode())


def test_telegram_posts_once_to_fixed_endpoint_and_destination() -> None:
    transport = RecordingTransport(200, b'{"ok":true,"result":{"message_id":42}}')
    adapter = TelegramHttpAdapter(
        bot_token=TELEGRAM_TOKEN,
        destinations={"alerts": "-100123"},
        transport=transport,
    )

    result = adapter.send_message("alerts", "hello")

    assert result == {"accepted": True, "provider": "telegram", "message_id": "42"}
    assert len(transport.calls) == 1
    request, timeout = transport.calls[0]
    assert request.method == "POST"
    assert request.full_url == (
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    )
    assert body_fields(request) == {"chat_id": ["-100123"], "text": ["hello"]}
    assert timeout == HTTP_TIMEOUT_SECONDS


def test_telegram_never_calls_unknown_destination() -> None:
    transport = RecordingTransport(200, b'{"ok":true}')
    adapter = TelegramHttpAdapter(
        bot_token=TELEGRAM_TOKEN,
        destinations={"alerts": "-100123"},
        transport=transport,
    )

    with pytest.raises(AdapterError) as captured:
        adapter.send_message("other", "hello")

    assert captured.value.code == "telegram_destination_not_configured"
    assert transport.calls == []


def test_trello_posts_credentials_in_header_and_not_url() -> None:
    transport = RecordingTransport(200, b'{"id":"card-42","name":"ignored"}')
    adapter = TrelloHttpAdapter(
        api_key=TRELLO_KEY,
        api_token=TRELLO_TOKEN,
        destinations={("portfolio", "inbox"): TRELLO_LIST_ID},
        transport=transport,
    )

    result = adapter.create_card("portfolio", "inbox", "Title", "Description")

    assert result == {"accepted": True, "provider": "trello", "card_id": "card-42"}
    assert len(transport.calls) == 1
    request, timeout = transport.calls[0]
    assert request.full_url == "https://api.trello.com/1/cards"
    assert TRELLO_KEY not in request.full_url
    assert TRELLO_TOKEN not in request.full_url
    assert body_fields(request) == {
        "idList": [TRELLO_LIST_ID],
        "name": ["Title"],
        "desc": ["Description"],
    }
    assert request.headers["Authorization"] == (
        f'OAuth oauth_consumer_key="{TRELLO_KEY}", oauth_token="{TRELLO_TOKEN}"'
    )
    assert timeout == HTTP_TIMEOUT_SECONDS


@pytest.mark.parametrize(
    ("adapter", "args", "expected_code"),
    [
        (
            TelegramHttpAdapter(
                bot_token=TELEGRAM_TOKEN,
                destinations={"alerts": "-100123"},
                transport=RecordingTransport(503, b"untrusted"),
            ),
            ("alerts", "hello"),
            "telegram_rejected",
        ),
        (
            TrelloHttpAdapter(
                api_key=TRELLO_KEY,
                api_token=TRELLO_TOKEN,
                destinations={("portfolio", "inbox"): TRELLO_LIST_ID},
                transport=RecordingTransport(401, b"untrusted"),
            ),
            ("portfolio", "inbox", "Title", "Description"),
            "trello_rejected",
        ),
    ],
)
def test_provider_failures_are_sanitized(
    adapter: Any, args: tuple[str, ...], expected_code: str
) -> None:
    method = (
        adapter.send_message
        if hasattr(adapter, "send_message")
        else adapter.create_card
    )

    with pytest.raises(AdapterError) as captured:
        method(*args)

    assert captured.value.code == expected_code
    assert "untrusted" not in str(captured.value)


@pytest.mark.parametrize(
    ("transport", "expected_code"),
    [
        (RaisingTransport(TimeoutError("secret timeout")), "telegram_outcome_unknown"),
        (RaisingTransport(URLError("secret network")), "telegram_outcome_unknown"),
        (RaisingTransport(RuntimeError("secret bug")), "telegram_unavailable"),
        (RecordingTransport(200, b"not-json"), "telegram_invalid_response"),
        (
            RecordingTransport(200, b"{" + b" " * (16 * 1024) + b"}"),
            "telegram_response_too_large",
        ),
        (
            RecordingTransport(200, b'{"ok":true,"result":{}}'),
            "telegram_invalid_response",
        ),
    ],
)
def test_telegram_faults_are_bounded_and_single_attempt(
    transport: Any, expected_code: str
) -> None:
    adapter = TelegramHttpAdapter(
        bot_token=TELEGRAM_TOKEN,
        destinations={"alerts": "-100123"},
        transport=transport,
    )

    with pytest.raises(AdapterError) as captured:
        adapter.send_message("alerts", "hello")

    assert captured.value.code == expected_code
    assert captured.value.retryable is False
    call_count = (
        transport.calls if isinstance(transport.calls, int) else len(transport.calls)
    )
    assert call_count == 1
    assert "secret" not in str(captured.value)


@pytest.mark.parametrize(
    ("response", "expected_code"),
    [
        (b"[]", "trello_invalid_response"),
        (b'{"name":"missing id"}', "trello_invalid_response"),
        (b'{"id":""}', "trello_invalid_response"),
        (b'{"id":"' + b"a" * 65 + b'"}', "trello_invalid_response"),
    ],
)
def test_trello_rejects_ambiguous_success_response(
    response: bytes, expected_code: str
) -> None:
    transport = RecordingTransport(200, response)
    adapter = TrelloHttpAdapter(
        api_key=TRELLO_KEY,
        api_token=TRELLO_TOKEN,
        destinations={("portfolio", "inbox"): TRELLO_LIST_ID},
        transport=transport,
    )

    with pytest.raises(AdapterError) as captured:
        adapter.create_card("portfolio", "inbox", "Title", "Description")

    assert captured.value.code == expected_code
    assert len(transport.calls) == 1


@pytest.mark.parametrize("list_id", ["", "list-123", "g" * 24, "a" * 25])
def test_trello_rejects_invalid_destination_identifier(list_id: str) -> None:
    with pytest.raises(ValueError, match="destinations"):
        TrelloHttpAdapter(
            api_key=TRELLO_KEY,
            api_token=TRELLO_TOKEN,
            destinations={("portfolio", "inbox"): list_id},
        )


def test_ssm_config_is_loaded_once_and_only_when_adapter_executes() -> None:
    ssm = FakeSsmClient(
        json.dumps(
            {
                "telegram": {
                    "bot_token": TELEGRAM_TOKEN,
                    "destinations": {"alerts": "-100123"},
                }
            }
        )
    )
    factory_calls: list[tuple[str, str]] = []

    def client_factory(service: str, region: str) -> FakeSsmClient:
        factory_calls.append((service, region))
        return ssm

    config = SsmIntegrationConfigProvider(
        parameter_name="/portfolio/aws-remote-mcp/dev/integrations",
        region="eu-west-1",
        client_factory=client_factory,
    )
    transport = RecordingTransport(200, b'{"ok":true,"result":{"message_id":7}}')
    adapter = SsmTelegramAdapter(config=config, transport=transport)

    assert factory_calls == []
    adapter.send_message("alerts", "one")
    adapter.send_message("alerts", "two")

    assert factory_calls == [("ssm", "eu-west-1")]
    assert ssm.calls == [
        {
            "Name": "/portfolio/aws-remote-mcp/dev/integrations",
            "WithDecryption": True,
        }
    ]
    assert len(transport.calls) == 2


@pytest.mark.parametrize(
    "client",
    [
        StaticSsmClient(RuntimeError("secret provider error")),
        StaticSsmClient({}),
        StaticSsmClient(
            {
                "Parameter": {
                    "Name": "/wrong/path",
                    "Type": "SecureString",
                    "Value": "{}",
                }
            }
        ),
        StaticSsmClient(
            {
                "Parameter": {
                    "Name": "/portfolio/aws-remote-mcp/dev/integrations",
                    "Type": "String",
                    "Value": "{}",
                }
            }
        ),
        StaticSsmClient(
            {
                "Parameter": {
                    "Name": "/portfolio/aws-remote-mcp/dev/integrations",
                    "Type": "SecureString",
                    "Value": "not-json-secret",
                }
            }
        ),
        StaticSsmClient(
            {
                "Parameter": {
                    "Name": "/portfolio/aws-remote-mcp/dev/integrations",
                    "Type": "SecureString",
                    "Value": "x" * 4097,
                }
            }
        ),
    ],
)
def test_ssm_configuration_failures_are_single_attempt_and_sanitized(
    client: StaticSsmClient,
) -> None:
    config = SsmIntegrationConfigProvider(
        parameter_name="/portfolio/aws-remote-mcp/dev/integrations",
        region="eu-west-1",
        client_factory=lambda _service, _region: client,
    )

    with pytest.raises(AdapterError) as captured:
        config.load()

    assert captured.value.code == "integration_config_unavailable"
    assert "secret" not in str(captured.value)
    assert client.calls == 1


def test_ssm_trello_config_maps_only_configured_alias() -> None:
    ssm = FakeSsmClient(
        json.dumps(
            {
                "trello": {
                    "api_key": TRELLO_KEY,
                    "api_token": TRELLO_TOKEN,
                    "destinations": [
                        {
                            "board": "portfolio",
                            "list": "inbox",
                            "list_id": TRELLO_LIST_ID,
                        }
                    ],
                }
            }
        )
    )
    config = SsmIntegrationConfigProvider(
        parameter_name="/portfolio/aws-remote-mcp/dev/integrations",
        region="eu-west-1",
        client_factory=lambda _service, _region: ssm,
    )
    transport = RecordingTransport(200, b'{"id":"card-7"}')
    adapter = SsmTrelloAdapter(config=config, transport=transport)

    result = adapter.create_card("portfolio", "inbox", "Title", "Description")

    assert result["card_id"] == "card-7"
    assert body_fields(transport.calls[0][0])["idList"] == [TRELLO_LIST_ID]


def test_ssm_trello_config_rejects_duplicate_aliases() -> None:
    ssm = FakeSsmClient(
        json.dumps(
            {
                "trello": {
                    "api_key": TRELLO_KEY,
                    "api_token": TRELLO_TOKEN,
                    "destinations": [
                        {
                            "board": "portfolio",
                            "list": "inbox",
                            "list_id": TRELLO_LIST_ID,
                        },
                        {
                            "board": "portfolio",
                            "list": "inbox",
                            "list_id": "abcdef0123456789abcdef01",
                        },
                    ],
                }
            }
        )
    )
    config = SsmIntegrationConfigProvider(
        parameter_name="/portfolio/aws-remote-mcp/dev/integrations",
        region="eu-west-1",
        client_factory=lambda _service, _region: ssm,
    )
    adapter = SsmTrelloAdapter(config=config)

    with pytest.raises(AdapterError) as captured:
        adapter.create_card("portfolio", "inbox", "Title", "Description")

    assert captured.value.code == "integration_config_invalid"
