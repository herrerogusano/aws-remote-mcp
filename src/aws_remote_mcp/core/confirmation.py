"""Short-lived, caller-bound, single-use confirmation records."""

from __future__ import annotations

import json
import secrets
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any, Protocol

from aws_remote_mcp.core.models import CallerContext, ConfirmationMetadata, JsonValue

DEFAULT_CONFIRMATION_TTL = timedelta(minutes=5)
MAX_CONFIRMATION_PAYLOAD_BYTES = 16_384


class ConfirmationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class ConfirmationProvider(Protocol):
    """Issue and atomically consume caller-bound confirmations."""

    def prepare(
        self,
        caller: CallerContext,
        action: str,
        payload: Mapping[str, JsonValue],
    ) -> ConfirmationMetadata: ...

    def consume(
        self,
        token: str,
        caller: CallerContext,
        action: str,
        payload: Mapping[str, JsonValue],
    ) -> None: ...


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


class DynamoDbConfirmationGuard:
    """Persist confirmations and consume them atomically across Lambda invocations."""

    def __init__(
        self,
        *,
        table_name: str,
        client: Any,
        ttl: timedelta = DEFAULT_CONFIRMATION_TTL,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not table_name:
            raise ValueError("Confirmation table name is required.")
        if ttl <= timedelta(0):
            raise ValueError("Confirmation TTL must be positive.")
        self._table_name = table_name
        self._client = client
        self._ttl = ttl
        self._clock = clock or (lambda: datetime.now(UTC))

    def prepare(
        self,
        caller: CallerContext,
        action: str,
        payload: Mapping[str, JsonValue],
    ) -> ConfirmationMetadata:
        now = self._aware_now()
        expires_epoch = int((now + self._ttl).timestamp())
        expires_at = datetime.fromtimestamp(expires_epoch, UTC)
        payload_digest = canonical_payload_digest(payload)
        token = secrets.token_urlsafe(32)
        try:
            self._client.put_item(
                TableName=self._table_name,
                Item={
                    "token_digest": {"S": self._token_digest(token)},
                    "caller_fingerprint": {"S": caller.fingerprint},
                    "action": {"S": action},
                    "payload_digest": {"S": payload_digest},
                    "expires_at": {"N": str(expires_epoch)},
                    "consumed": {"BOOL": False},
                },
                ConditionExpression="attribute_not_exists(token_digest)",
            )
        except Exception as error:
            raise ConfirmationError(
                "confirmation_store_unavailable",
                "Confirmation could not be stored.",
            ) from error
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
        now_epoch = int(self._aware_now().timestamp())
        key = {"token_digest": {"S": self._token_digest(token)}}
        try:
            self._client.update_item(
                TableName=self._table_name,
                Key=key,
                UpdateExpression="SET consumed = :true",
                ConditionExpression=(
                    "attribute_exists(token_digest) AND consumed = :false "
                    "AND expires_at > :now AND caller_fingerprint = :caller "
                    "AND #action = :action AND payload_digest = :payload"
                ),
                ExpressionAttributeNames={"#action": "action"},
                ExpressionAttributeValues={
                    ":true": {"BOOL": True},
                    ":false": {"BOOL": False},
                    ":now": {"N": str(now_epoch)},
                    ":caller": {"S": caller.fingerprint},
                    ":action": {"S": action},
                    ":payload": {"S": canonical_payload_digest(payload)},
                },
            )
            return
        except Exception as error:
            if not self._is_conditional_failure(error):
                raise ConfirmationError(
                    "confirmation_store_unavailable",
                    "Confirmation could not be consumed.",
                ) from error

        record = self._read_record(key)
        if record is None:
            raise ConfirmationError("confirmation_invalid", "Confirmation is invalid.")
        if self._attribute(record, "consumed", "BOOL") is True:
            raise ConfirmationError(
                "confirmation_replayed", "Confirmation has already been consumed."
            )
        expires_at = self._number_attribute(record, "expires_at")
        if expires_at <= now_epoch:
            raise ConfirmationError("confirmation_expired", "Confirmation has expired.")
        if self._attribute(record, "caller_fingerprint", "S") != caller.fingerprint:
            raise ConfirmationError(
                "confirmation_caller_mismatch",
                "Confirmation belongs to a different caller.",
            )
        if self._attribute(record, "action", "S") != action:
            raise ConfirmationError(
                "confirmation_action_mismatch",
                "Confirmation does not authorize this action.",
            )
        raise ConfirmationError(
            "confirmation_payload_mismatch",
            "Confirmation does not authorize this payload.",
        )

    def _read_record(self, key: dict[str, dict[str, str]]) -> dict[str, Any] | None:
        try:
            response = self._client.get_item(
                TableName=self._table_name,
                Key=key,
                ConsistentRead=True,
            )
        except Exception as error:
            raise ConfirmationError(
                "confirmation_store_unavailable",
                "Confirmation state could not be read.",
            ) from error
        item = response.get("Item")
        return item if isinstance(item, dict) else None

    def _aware_now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None:
            raise ValueError(
                "Confirmation clock must return a timezone-aware datetime."
            )
        return value

    @staticmethod
    def _is_conditional_failure(error: Exception) -> bool:
        response = getattr(error, "response", None)
        if not isinstance(response, dict):
            return False
        details = response.get("Error")
        return isinstance(details, dict) and details.get("Code") == (
            "ConditionalCheckFailedException"
        )

    @staticmethod
    def _attribute(item: dict[str, Any], name: str, kind: str) -> Any:
        value = item.get(name)
        if not isinstance(value, dict) or kind not in value:
            raise ConfirmationError(
                "confirmation_store_invalid", "Confirmation state is invalid."
            )
        return value[kind]

    @classmethod
    def _number_attribute(cls, item: dict[str, Any], name: str) -> int:
        value = cls._attribute(item, name, "N")
        try:
            return int(value)
        except (TypeError, ValueError) as error:
            raise ConfirmationError(
                "confirmation_store_invalid", "Confirmation state is invalid."
            ) from error

    @staticmethod
    def _token_digest(token: str) -> str:
        return sha256(token.encode()).hexdigest()
