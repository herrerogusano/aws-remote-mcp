"""Application handlers with no MCP, HTTP, AWS, or third-party coupling."""

from __future__ import annotations

import json
from collections.abc import Mapping

from aws_remote_mcp.adapters.protocols import (
    AdapterError,
    AwsAdapter,
    TelegramAdapter,
    TrelloAdapter,
)
from aws_remote_mcp.core.confirmation import ConfirmationError, ConfirmationGuard
from aws_remote_mcp.core.models import (
    CallerContext,
    JsonValue,
    OperationCounters,
    ToolIssue,
    ToolResult,
)
from aws_remote_mcp.core.operations import OperationBlockedError, OperationRegistry

MAX_RESULT_BYTES = 64 * 1024
MAX_MESSAGE_CHARS = 4096
MAX_CARD_TITLE_CHARS = 256
MAX_CARD_DESCRIPTION_CHARS = 5000


class ToolService:
    def __init__(
        self,
        *,
        operations: OperationRegistry,
        confirmations: ConfirmationGuard,
        aws: AwsAdapter,
        telegram: TelegramAdapter,
        trello: TrelloAdapter,
        telegram_destinations: frozenset[str],
        trello_destinations: frozenset[tuple[str, str]],
        max_result_bytes: int = MAX_RESULT_BYTES,
    ) -> None:
        if max_result_bytes <= 0:
            raise ValueError("Result size limit must be positive.")
        self._operations = operations
        self._confirmations = confirmations
        self._aws = aws
        self._telegram = telegram
        self._trello = trello
        self._telegram_destinations = telegram_destinations
        self._trello_destinations = trello_destinations
        self._max_result_bytes = max_result_bytes

    def run_aws_operation(
        self,
        operation: str,
        arguments: Mapping[str, JsonValue],
    ) -> ToolResult:
        counters = OperationCounters()
        try:
            self._operations.require_automatic(operation)
        except OperationBlockedError as error:
            return ToolResult(
                status="error",
                errors=(ToolIssue("operation_blocked", str(error)),),
                counters=counters,
            )
        counters.sdk_requests += 1
        try:
            response = self._aws.execute(operation, arguments)
        except AdapterError as error:
            return self._adapter_failure(error, counters)
        return self._bounded_result(response, counters)

    def prepare_telegram_message(
        self, caller: CallerContext, destination: str, message: str
    ) -> ToolResult:
        issue = self._validate_telegram(destination, message)
        if issue is not None:
            return ToolResult(status="error", errors=(issue,))
        payload: dict[str, JsonValue] = {
            "destination": destination,
            "message": message,
        }
        confirmation = self._confirmations.prepare(
            caller, "telegram.send_message", payload
        )
        return ToolResult(
            status="confirmation_required",
            data={"preview": payload},
            confirmation=confirmation,
        )

    def execute_telegram_message(
        self,
        caller: CallerContext,
        token: str,
        destination: str,
        message: str,
    ) -> ToolResult:
        issue = self._validate_telegram(destination, message)
        if issue is not None:
            return ToolResult(status="error", errors=(issue,))
        payload: dict[str, JsonValue] = {
            "destination": destination,
            "message": message,
        }
        counters = OperationCounters()
        confirmation_error = self._consume_confirmation(
            token, caller, "telegram.send_message", payload
        )
        if confirmation_error is not None:
            return ToolResult(
                status="error", errors=(confirmation_error,), counters=counters
            )
        counters.record_external_write_attempt()
        try:
            response = self._telegram.send_message(destination, message)
        except AdapterError as error:
            return self._adapter_failure(error, counters)
        counters.external_writes_succeeded += 1
        return self._bounded_result(response, counters)

    def prepare_trello_card(
        self,
        caller: CallerContext,
        board: str,
        list_name: str,
        title: str,
        description: str,
    ) -> ToolResult:
        issue = self._validate_trello(board, list_name, title, description)
        if issue is not None:
            return ToolResult(status="error", errors=(issue,))
        payload = self._trello_payload(board, list_name, title, description)
        confirmation = self._confirmations.prepare(
            caller, "trello.create_card", payload
        )
        return ToolResult(
            status="confirmation_required",
            data={"preview": payload},
            confirmation=confirmation,
        )

    def execute_trello_card(
        self,
        caller: CallerContext,
        token: str,
        board: str,
        list_name: str,
        title: str,
        description: str,
    ) -> ToolResult:
        issue = self._validate_trello(board, list_name, title, description)
        if issue is not None:
            return ToolResult(status="error", errors=(issue,))
        payload = self._trello_payload(board, list_name, title, description)
        counters = OperationCounters()
        confirmation_error = self._consume_confirmation(
            token, caller, "trello.create_card", payload
        )
        if confirmation_error is not None:
            return ToolResult(
                status="error", errors=(confirmation_error,), counters=counters
            )
        counters.record_external_write_attempt()
        try:
            response = self._trello.create_card(board, list_name, title, description)
        except AdapterError as error:
            return self._adapter_failure(error, counters)
        counters.external_writes_succeeded += 1
        return self._bounded_result(response, counters)

    def _bounded_result(
        self, data: dict[str, JsonValue], counters: OperationCounters
    ) -> ToolResult:
        encoded = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode()
        if len(encoded) > self._max_result_bytes:
            return ToolResult(
                status="error",
                errors=(
                    ToolIssue(
                        "result_too_large",
                        "Adapter result exceeded the configured response limit.",
                    ),
                ),
                counters=counters,
            )
        return ToolResult(status="ok", data=data, counters=counters)

    @staticmethod
    def _adapter_failure(
        error: AdapterError, counters: OperationCounters
    ) -> ToolResult:
        return ToolResult(
            status="error",
            errors=(ToolIssue(error.code, str(error), retryable=error.retryable),),
            counters=counters,
        )

    def _consume_confirmation(
        self,
        token: str,
        caller: CallerContext,
        action: str,
        payload: Mapping[str, JsonValue],
    ) -> ToolIssue | None:
        try:
            self._confirmations.consume(token, caller, action, payload)
        except ConfirmationError as error:
            return ToolIssue(error.code, str(error))
        return None

    def _validate_telegram(self, destination: str, message: str) -> ToolIssue | None:
        if destination not in self._telegram_destinations:
            return ToolIssue(
                "destination_not_allowed", "Telegram destination is not allowed."
            )
        if not message or len(message) > MAX_MESSAGE_CHARS:
            return ToolIssue("invalid_message", "Telegram message length is invalid.")
        return None

    def _validate_trello(
        self, board: str, list_name: str, title: str, description: str
    ) -> ToolIssue | None:
        if (board, list_name) not in self._trello_destinations:
            return ToolIssue(
                "destination_not_allowed", "Trello destination is not allowed."
            )
        if not title or len(title) > MAX_CARD_TITLE_CHARS:
            return ToolIssue("invalid_title", "Trello card title length is invalid.")
        if len(description) > MAX_CARD_DESCRIPTION_CHARS:
            return ToolIssue(
                "invalid_description", "Trello card description length is invalid."
            )
        return None

    @staticmethod
    def _trello_payload(
        board: str, list_name: str, title: str, description: str
    ) -> dict[str, JsonValue]:
        return {
            "board": board,
            "list": list_name,
            "title": title,
            "description": description,
        }
