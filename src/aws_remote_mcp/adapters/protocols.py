"""Ports implemented by fake adapters now and real adapters in later phases."""

from collections.abc import Mapping
from typing import Protocol

from aws_remote_mcp.core.models import JsonValue


class AdapterError(RuntimeError):
    """Sanitized downstream failure safe to translate into a tool result."""

    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        self.code = code
        self.retryable = retryable
        super().__init__(message)


class AwsAdapter(Protocol):
    def execute(
        self, operation: str, arguments: Mapping[str, JsonValue]
    ) -> dict[str, JsonValue]: ...


class TelegramAdapter(Protocol):
    def send_message(self, destination: str, message: str) -> dict[str, JsonValue]: ...


class TrelloAdapter(Protocol):
    def create_card(
        self,
        board: str,
        list_name: str,
        title: str,
        description: str,
    ) -> dict[str, JsonValue]: ...
