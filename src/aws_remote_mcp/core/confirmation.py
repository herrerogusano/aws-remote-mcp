"""Short-lived, caller-bound, single-use confirmation records."""

from __future__ import annotations

import json
import secrets
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256

from aws_remote_mcp.core.models import CallerContext, ConfirmationMetadata, JsonValue

DEFAULT_CONFIRMATION_TTL = timedelta(minutes=5)
MAX_CONFIRMATION_PAYLOAD_BYTES = 16_384


class ConfirmationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(slots=True)
class _ConfirmationRecord:
    caller_fingerprint: str
    action: str
    payload_digest: str
    expires_at: datetime
    consumed: bool = False


def canonical_payload_digest(payload: Mapping[str, JsonValue]) -> str:
    try:
        encoded = json.dumps(
            payload,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
    except (TypeError, ValueError) as error:
        raise ConfirmationError(
            "invalid_payload", "Payload is not canonical JSON."
        ) from error
    if len(encoded) > MAX_CONFIRMATION_PAYLOAD_BYTES:
        raise ConfirmationError(
            "payload_too_large", "Confirmation payload is too large."
        )
    return sha256(encoded).hexdigest()


class ConfirmationGuard:
    """Issue opaque tokens and consume each exact confirmation at most once."""

    def __init__(
        self,
        *,
        ttl: timedelta = DEFAULT_CONFIRMATION_TTL,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if ttl <= timedelta(0):
            raise ValueError("Confirmation TTL must be positive.")
        self._ttl = ttl
        self._clock = clock or (lambda: datetime.now(UTC))
        self._records: dict[str, _ConfirmationRecord] = {}

    def prepare(
        self,
        caller: CallerContext,
        action: str,
        payload: Mapping[str, JsonValue],
    ) -> ConfirmationMetadata:
        now = self._aware_now()
        expires_at = now + self._ttl
        payload_digest = canonical_payload_digest(payload)
        token = secrets.token_urlsafe(32)
        self._records[self._token_digest(token)] = _ConfirmationRecord(
            caller_fingerprint=caller.fingerprint,
            action=action,
            payload_digest=payload_digest,
            expires_at=expires_at,
        )
        return ConfirmationMetadata(
            token=token,
            action=action,
            payload_digest=payload_digest,
            expires_at=expires_at.isoformat(),
        )

    def consume(
        self,
        token: str,
        caller: CallerContext,
        action: str,
        payload: Mapping[str, JsonValue],
    ) -> None:
        record = self._records.get(self._token_digest(token))
        if record is None:
            raise ConfirmationError("confirmation_invalid", "Confirmation is invalid.")
        if record.consumed:
            raise ConfirmationError(
                "confirmation_replayed", "Confirmation has already been consumed."
            )
        if self._aware_now() >= record.expires_at:
            raise ConfirmationError("confirmation_expired", "Confirmation has expired.")
        if record.caller_fingerprint != caller.fingerprint:
            raise ConfirmationError(
                "confirmation_caller_mismatch",
                "Confirmation belongs to a different caller.",
            )
        if record.action != action:
            raise ConfirmationError(
                "confirmation_action_mismatch",
                "Confirmation does not authorize this action.",
            )
        if record.payload_digest != canonical_payload_digest(payload):
            raise ConfirmationError(
                "confirmation_payload_mismatch",
                "Confirmation does not authorize this payload.",
            )
        record.consumed = True

    def _aware_now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None:
            raise ValueError(
                "Confirmation clock must return a timezone-aware datetime."
            )
        return value

    @staticmethod
    def _token_digest(token: str) -> str:
        return sha256(token.encode()).hexdigest()
