"""Single-attempt Telegram and Trello adapters with sanitized results."""

from __future__ import annotations

import importlib
import json
import re
from collections.abc import Callable, Mapping
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from aws_remote_mcp.adapters.protocols import AdapterError
from aws_remote_mcp.core.models import JsonValue

HTTP_TIMEOUT_SECONDS = 4.0
MAX_PROVIDER_RESPONSE_BYTES = 16 * 1024
TELEGRAM_TOKEN_PATTERN = re.compile(r"^[0-9]{5,20}:[A-Za-z0-9_-]{20,128}$")
TELEGRAM_CHAT_PATTERN = re.compile(r"^(?:-?[0-9]{1,20}|@[A-Za-z0-9_]{5,32})$")
TRELLO_CREDENTIAL_PATTERN = re.compile(r"^[A-Za-z0-9_-]{8,256}$")

type HttpTransport = Callable[[Request, float], tuple[int, bytes]]
type AwsClientFactory = Callable[[str, str], Any]


def _aws_client(service: str, region: str) -> Any:
    boto3 = importlib.import_module("boto3")
    config_module = importlib.import_module("botocore.config")
    config = config_module.Config(
        connect_timeout=2,
        read_timeout=3,
        retries={"total_max_attempts": 1, "mode": "standard"},
    )
    return boto3.client(service, region_name=region, config=config)


def _http_transport(request: Request, timeout: float) -> tuple[int, bytes]:
    with urlopen(request, timeout=timeout) as response:
        body = response.read(MAX_PROVIDER_RESPONSE_BYTES + 1)
        return response.status, body


def _json_object(body: bytes, provider: str) -> dict[str, Any]:
    if len(body) > MAX_PROVIDER_RESPONSE_BYTES:
        raise AdapterError(
            f"{provider}_response_too_large",
            f"{provider.title()} returned an oversized response.",
        )
    try:
        decoded = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AdapterError(
            f"{provider}_invalid_response",
            f"{provider.title()} returned an invalid response.",
        ) from error
    if not isinstance(decoded, dict):
        raise AdapterError(
            f"{provider}_invalid_response",
            f"{provider.title()} returned an invalid response.",
        )
    return decoded


def _execute_once(
    request: Request,
    *,
    provider: str,
    transport: HttpTransport,
) -> dict[str, Any]:
    try:
        status, body = transport(request, HTTP_TIMEOUT_SECONDS)
    except HTTPError as error:
        raise AdapterError(
            f"{provider}_rejected",
            f"{provider.title()} rejected the request.",
        ) from error
    except (TimeoutError, URLError, OSError) as error:
        raise AdapterError(
            f"{provider}_outcome_unknown",
            f"{provider.title()} did not confirm the write outcome.",
            retryable=False,
        ) from error
    except Exception as error:
        raise AdapterError(
            f"{provider}_unavailable",
            f"{provider.title()} could not process the request.",
        ) from error
    if not 200 <= status < 300:
        raise AdapterError(
            f"{provider}_rejected",
            f"{provider.title()} rejected the request.",
        )
    return _json_object(body, provider)


class TelegramHttpAdapter:
    """Send one message to an alias mapped to one fixed Telegram chat."""

    def __init__(
        self,
        *,
        bot_token: str,
        destinations: Mapping[str, str],
        transport: HttpTransport = _http_transport,
    ) -> None:
        if TELEGRAM_TOKEN_PATTERN.fullmatch(bot_token) is None:
            raise ValueError("Telegram bot token format is invalid.")
        if not destinations or any(
            not isinstance(alias, str)
            or not alias
            or not isinstance(chat, str)
            or TELEGRAM_CHAT_PATTERN.fullmatch(chat) is None
            for alias, chat in destinations.items()
        ):
            raise ValueError("Telegram destinations are invalid.")
        self._endpoint = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        self._destinations = dict(destinations)
        self._transport = transport

    def send_message(self, destination: str, message: str) -> dict[str, JsonValue]:
        chat_id = self._destinations.get(destination)
        if chat_id is None:
            raise AdapterError(
                "telegram_destination_not_configured",
                "Telegram destination is not configured.",
            )
        request = Request(
            self._endpoint,
            data=urlencode({"chat_id": chat_id, "text": message}).encode(),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        response = _execute_once(
            request, provider="telegram", transport=self._transport
        )
        if response.get("ok") is not True:
            raise AdapterError("telegram_rejected", "Telegram rejected the request.")
        result = response.get("result")
        message_id = result.get("message_id") if isinstance(result, dict) else None
        return {
            "accepted": True,
            "provider": "telegram",
            "message_id": str(message_id)[:64] if message_id is not None else "unknown",
        }


class TrelloHttpAdapter:
    """Create one card in an alias mapped to one fixed Trello list."""

    def __init__(
        self,
        *,
        api_key: str,
        api_token: str,
        destinations: Mapping[tuple[str, str], str],
        transport: HttpTransport = _http_transport,
    ) -> None:
        if (
            TRELLO_CREDENTIAL_PATTERN.fullmatch(api_key) is None
            or TRELLO_CREDENTIAL_PATTERN.fullmatch(api_token) is None
        ):
            raise ValueError("Trello credential format is invalid.")
        if not destinations or any(
            not board or not list_name or not list_id
            for (board, list_name), list_id in destinations.items()
        ):
            raise ValueError("Trello destinations are invalid.")
        self._authorization = (
            f'OAuth oauth_consumer_key="{api_key}", oauth_token="{api_token}"'
        )
        self._destinations = dict(destinations)
        self._transport = transport

    def create_card(
        self,
        board: str,
        list_name: str,
        title: str,
        description: str,
    ) -> dict[str, JsonValue]:
        list_id = self._destinations.get((board, list_name))
        if list_id is None:
            raise AdapterError(
                "trello_destination_not_configured",
                "Trello destination is not configured.",
            )
        request = Request(
            "https://api.trello.com/1/cards",
            data=urlencode(
                {"idList": list_id, "name": title, "desc": description}
            ).encode(),
            headers={
                "Accept": "application/json",
                "Authorization": self._authorization,
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method="POST",
        )
        response = _execute_once(request, provider="trello", transport=self._transport)
        card_id = response.get("id")
        return {
            "accepted": True,
            "provider": "trello",
            "card_id": str(card_id)[:64] if card_id is not None else "unknown",
        }


class SsmIntegrationConfigProvider:
    """Load one bounded SecureString JSON document on the first external write."""

    def __init__(
        self,
        *,
        parameter_name: str,
        region: str,
        client_factory: AwsClientFactory = _aws_client,
    ) -> None:
        if not parameter_name.startswith("/portfolio/aws-remote-mcp/dev/"):
            raise ValueError("Integration parameter path is outside the DEV namespace.")
        if region != "eu-west-1":
            raise ValueError("Integration configuration is restricted to eu-west-1.")
        self._parameter_name = parameter_name
        self._region = region
        self._client_factory = client_factory
        self._cached: dict[str, Any] | None = None

    def load(self) -> dict[str, Any]:
        if self._cached is not None:
            return self._cached
        try:
            client = self._client_factory("ssm", self._region)
            response = client.get_parameter(
                Name=self._parameter_name,
                WithDecryption=True,
            )
            parameter = response.get("Parameter")
            if (
                not isinstance(parameter, dict)
                or parameter.get("Name") != self._parameter_name
                or parameter.get("Type") != "SecureString"
            ):
                raise ValueError("Invalid parameter metadata.")
            value = parameter.get("Value")
            if not isinstance(value, str) or len(value.encode()) > 4096:
                raise ValueError("Invalid parameter value.")
            config = json.loads(value)
            if not isinstance(config, dict):
                raise ValueError("Invalid integration configuration.")
        except Exception as error:
            raise AdapterError(
                "integration_config_unavailable",
                "External integration configuration is unavailable.",
            ) from error
        self._cached = config
        return config


class SsmTelegramAdapter:
    """Resolve Telegram credentials only after a confirmation is consumed."""

    def __init__(
        self,
        *,
        config: SsmIntegrationConfigProvider,
        transport: HttpTransport = _http_transport,
    ) -> None:
        self._config = config
        self._transport = transport

    def send_message(self, destination: str, message: str) -> dict[str, JsonValue]:
        root = self._config.load().get("telegram")
        if not isinstance(root, dict):
            raise AdapterError(
                "integration_config_invalid",
                "Telegram configuration is invalid.",
            )
        token = root.get("bot_token")
        destinations = root.get("destinations")
        if not isinstance(token, str) or not isinstance(destinations, dict):
            raise AdapterError(
                "integration_config_invalid",
                "Telegram configuration is invalid.",
            )
        try:
            adapter = TelegramHttpAdapter(
                bot_token=token,
                destinations=destinations,
                transport=self._transport,
            )
        except ValueError as error:
            raise AdapterError(
                "integration_config_invalid",
                "Telegram configuration is invalid.",
            ) from error
        return adapter.send_message(destination, message)


class SsmTrelloAdapter:
    """Resolve Trello credentials only after a confirmation is consumed."""

    def __init__(
        self,
        *,
        config: SsmIntegrationConfigProvider,
        transport: HttpTransport = _http_transport,
    ) -> None:
        self._config = config
        self._transport = transport

    def create_card(
        self,
        board: str,
        list_name: str,
        title: str,
        description: str,
    ) -> dict[str, JsonValue]:
        root = self._config.load().get("trello")
        if not isinstance(root, dict):
            raise AdapterError(
                "integration_config_invalid", "Trello configuration is invalid."
            )
        api_key = root.get("api_key")
        api_token = root.get("api_token")
        raw_destinations = root.get("destinations")
        if (
            not isinstance(api_key, str)
            or not isinstance(api_token, str)
            or not isinstance(raw_destinations, list)
        ):
            raise AdapterError(
                "integration_config_invalid", "Trello configuration is invalid."
            )
        destinations: dict[tuple[str, str], str] = {}
        for item in raw_destinations:
            if not isinstance(item, dict):
                raise AdapterError(
                    "integration_config_invalid", "Trello configuration is invalid."
                )
            board_alias = item.get("board")
            list_alias = item.get("list")
            list_id = item.get("list_id")
            if (
                not isinstance(board_alias, str)
                or not isinstance(list_alias, str)
                or not isinstance(list_id, str)
            ):
                raise AdapterError(
                    "integration_config_invalid", "Trello configuration is invalid."
                )
            destinations[(board_alias, list_alias)] = list_id
        try:
            adapter = TrelloHttpAdapter(
                api_key=api_key,
                api_token=api_token,
                destinations=destinations,
                transport=self._transport,
            )
        except ValueError as error:
            raise AdapterError(
                "integration_config_invalid", "Trello configuration is invalid."
            ) from error
        return adapter.create_card(board, list_name, title, description)
