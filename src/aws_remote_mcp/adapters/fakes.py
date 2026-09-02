"""Deterministic in-memory adapters for offline application tests."""

from collections.abc import Mapping
from dataclasses import dataclass, field

from aws_remote_mcp.adapters.protocols import AdapterError, AwsAdapterResult
from aws_remote_mcp.core.models import JsonValue


@dataclass(slots=True)
class FakeAwsAdapter:
    responses: dict[str, AwsAdapterResult] = field(default_factory=dict)
    failures: dict[str, AdapterError] = field(default_factory=dict)
    calls: list[tuple[str, dict[str, JsonValue]]] = field(default_factory=list)

    def execute(
        self, operation: str, arguments: Mapping[str, JsonValue]
    ) -> AwsAdapterResult:
        self.calls.append((operation, dict(arguments)))
        if error := self.failures.get(operation):
            raise error
        return self.responses.get(
            operation,
            AwsAdapterResult(
                data={"operation": operation}, sdk_requests=0, resources=0
            ),
        )


@dataclass(slots=True)
class FakeTelegramAdapter:
    calls: list[tuple[str, str]] = field(default_factory=list)
    failure: AdapterError | None = None

    def send_message(self, destination: str, message: str) -> dict[str, JsonValue]:
        self.calls.append((destination, message))
        if self.failure is not None:
            raise self.failure
        return {"accepted": True, "message_id": f"fake-{len(self.calls)}"}


@dataclass(slots=True)
class FakeTrelloAdapter:
    calls: list[tuple[str, str, str, str]] = field(default_factory=list)
    failure: AdapterError | None = None

    def create_card(
        self,
        board: str,
        list_name: str,
        title: str,
        description: str,
    ) -> dict[str, JsonValue]:
        self.calls.append((board, list_name, title, description))
        if self.failure is not None:
            raise self.failure
        return {"accepted": True, "card_id": f"fake-{len(self.calls)}"}
