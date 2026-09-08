"""Structured audit records expose only an explicit safe schema."""

import pytest

from aws_remote_mcp.core.audit import build_tool_audit_record
from aws_remote_mcp.core.models import (
    CallerContext,
    ConfirmationMetadata,
    OperationCounters,
    ToolIssue,
    ToolResult,
)


def test_audit_record_omits_payload_confirmation_and_provider_data() -> None:
    secret = "must-not-appear"
    result = ToolResult(
        status="error",
        data={"provider_response": secret},
        errors=(ToolIssue("provider_rejected", secret),),
        counters=OperationCounters(external_writes_attempted=1),
        confirmation=ConfirmationMetadata(
            token=secret,
            action="telegram.send_message",
            payload_digest=secret,
            expires_at="2026-09-08T17:00:00+00:00",
        ),
    )

    caller = CallerContext("https://issuer.example", "caller-1")
    record = build_tool_audit_record(
        tool="enviar_mensaje_telegram",
        result=result,
        caller=caller,
        environment="dev",
        request_id="request-1",
    )

    assert record == {
        "schema_version": 1,
        "event_type": "mcp_tool_result",
        "environment": "dev",
        "request_id": "request-1",
        "caller_fingerprint": caller.fingerprint,
        "tool": "enviar_mensaje_telegram",
        "status": "error",
        "warning_codes": [],
        "error_codes": ["provider_rejected"],
        "counters": {
            "sdk_requests": 0,
            "resources": 0,
            "external_writes_attempted": 1,
            "external_writes_succeeded": 0,
        },
    }
    assert secret not in str(record)


@pytest.mark.parametrize(
    ("tool", "environment", "request_id"),
    [
        ("unknown", "dev", "request-1"),
        ("diagnostico", "dev with spaces", "request-1"),
        ("diagnostico", "dev", ""),
    ],
)
def test_audit_record_rejects_unbounded_context(
    tool: str, environment: str, request_id: str
) -> None:
    with pytest.raises(ValueError):
        build_tool_audit_record(
            tool=tool,
            result=ToolResult(status="ok"),
            caller=CallerContext("https://issuer.example", "caller-1"),
            environment=environment,
            request_id=request_id,
        )


def test_audit_record_sanitizes_and_bounds_issue_codes() -> None:
    result = ToolResult(
        status="error",
        errors=tuple(
            ToolIssue("secret value" if index == 0 else f"error_{index}", "hidden")
            for index in range(12)
        ),
    )

    record = build_tool_audit_record(
        tool="diagnostico",
        result=result,
        caller=CallerContext("https://issuer.example", "caller-1"),
        environment="dev",
        request_id="request-1",
    )

    assert record["error_codes"] == [
        "invalid_issue_code",
        "error_1",
        "error_2",
        "error_3",
        "error_4",
        "error_5",
        "error_6",
        "error_7",
    ]
