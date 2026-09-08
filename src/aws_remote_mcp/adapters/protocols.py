"""Ports implemented by offline fakes and later by reviewed live adapters."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, Protocol

from aws_remote_mcp.core.models import JsonValue


class AdapterError(RuntimeError):
    """Sanitized downstream failure safe to translate into a tool result."""

    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        self.code = code
        self.retryable = retryable
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class AdapterIssue:
    code: str
    message: str
    retryable: bool = False


@dataclass(frozen=True, slots=True)
class AwsAdapterResult:
    data: dict[str, JsonValue]
    sdk_requests: int
    resources: int
    status: Literal["ok", "partial", "error"] = "ok"
    issues: tuple[AdapterIssue, ...] = ()

    def __post_init__(self) -> None:
        if self.sdk_requests < 0 or self.resources < 0:
            raise ValueError("AWS adapter counters cannot be negative.")
        if self.status == "ok" and self.issues:
            raise ValueError("Successful AWS adapter results cannot contain issues.")
        if self.status != "ok" and not self.issues:
            raise ValueError("Non-success AWS adapter results require an issue.")


class AwsAdapter(Protocol):
    def execute(
        self, operation: str, arguments: Mapping[str, JsonValue]
    ) -> AwsAdapterResult: ...


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
