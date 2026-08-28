"""Normalized application models shared by every future transport."""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from typing import Literal

type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]
type ToolStatus = Literal["ok", "partial", "error", "confirmation_required"]


@dataclass(frozen=True, slots=True)
class CallerContext:
    """Validated caller identity without retaining an inbound bearer token."""

    issuer: str
    subject: str
    scopes: frozenset[str] = frozenset()

    @property
    def fingerprint(self) -> str:
        material = f"{self.issuer}\x00{self.subject}".encode()
        return sha256(material).hexdigest()[:24]


@dataclass(frozen=True, slots=True)
class ToolIssue:
    code: str
    message: str
    retryable: bool = False


@dataclass(slots=True)
class OperationCounters:
    sdk_requests: int = 0
    resources: int = 0
    external_writes_attempted: int = 0
    external_writes_succeeded: int = 0

    def record_external_write_attempt(self) -> None:
        if self.external_writes_attempted >= 1:
            raise WriteLimitExceededError
        self.external_writes_attempted += 1


class WriteLimitExceededError(RuntimeError):
    """Raised before a second external write can occur in one execution."""

    def __init__(self) -> None:
        super().__init__("At most one external write is allowed per execution.")


@dataclass(frozen=True, slots=True)
class ConfirmationMetadata:
    token: str
    action: str
    payload_digest: str
    expires_at: str


@dataclass(frozen=True, slots=True)
class ToolResult:
    status: ToolStatus
    data: dict[str, JsonValue] = field(default_factory=dict)
    warnings: tuple[ToolIssue, ...] = ()
    errors: tuple[ToolIssue, ...] = ()
    counters: OperationCounters = field(default_factory=OperationCounters)
    confirmation: ConfirmationMetadata | None = None
