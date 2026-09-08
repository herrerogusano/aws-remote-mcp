"""Allowlisted structured audit records for MCP tool outcomes."""

from __future__ import annotations

import re
from collections.abc import Mapping

from aws_remote_mcp.core.models import CallerContext, JsonValue, ToolResult

AUDITED_TOOLS = frozenset(
    {
        "diagnostico",
        "listar_inventario_aws",
        "preparar_mensaje_telegram",
        "enviar_mensaje_telegram",
        "preparar_tarjeta_trello",
        "crear_tarjeta_trello",
    }
)
SAFE_CONTEXT_PATTERN = re.compile(r"^[A-Za-z0-9._:/-]{1,128}$")
SAFE_ISSUE_CODE_PATTERN = re.compile(r"^[a-z0-9_]{1,64}$")
MAX_ISSUE_CODES = 8


def _safe_issue_codes(result_codes: list[str]) -> list[JsonValue]:
    return [
        code if SAFE_ISSUE_CODE_PATTERN.fullmatch(code) else "invalid_issue_code"
        for code in result_codes[:MAX_ISSUE_CODES]
    ]


def build_tool_audit_record(
    *,
    tool: str,
    result: ToolResult,
    caller: CallerContext,
    environment: str,
    request_id: str,
) -> Mapping[str, JsonValue]:
    """Return a fixed-schema record that cannot include tool inputs or secrets."""

    if tool not in AUDITED_TOOLS:
        raise ValueError("Audit tool name is not allowlisted.")
    if SAFE_CONTEXT_PATTERN.fullmatch(environment) is None:
        raise ValueError("Audit environment is invalid.")
    if SAFE_CONTEXT_PATTERN.fullmatch(request_id) is None:
        raise ValueError("Audit request identifier is invalid.")

    return {
        "schema_version": 1,
        "event_type": "mcp_tool_result",
        "environment": environment,
        "request_id": request_id,
        "caller_fingerprint": caller.fingerprint,
        "tool": tool,
        "status": result.status,
        "warning_codes": _safe_issue_codes([issue.code for issue in result.warnings]),
        "error_codes": _safe_issue_codes([issue.code for issue in result.errors]),
        "counters": {
            "sdk_requests": result.counters.sdk_requests,
            "resources": result.counters.resources,
            "external_writes_attempted": result.counters.external_writes_attempted,
            "external_writes_succeeded": result.counters.external_writes_succeeded,
        },
    }
