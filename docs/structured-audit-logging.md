# Structured tool audit logging

## Purpose

The Lambda runtime emits one allowlisted JSON audit record after each completed
MCP tool call. The record supports operational review without turning CloudWatch
into a secondary store for tool payloads or credentials.

## Schema

Each record contains only:

- fixed schema version and event type;
- environment and Lambda request identifier;
- the SHA-256-derived caller fingerprint already used for confirmation binding;
- one allowlisted tool name and normalized result status;
- warning and error codes, never their messages;
- bounded SDK, resource and external-write counters.

The builder does not accept tool arguments, result data, preview data,
confirmation metadata, provider responses, bearer tokens, downstream
credentials or destination identifiers. Unknown tool names and malformed
context fields are rejected before logging.

## Failure behavior

Audit emission occurs after the tool result exists. A logging failure must not
replace that result, especially after an external provider has accepted a write:
returning an ambiguous error could encourage a duplicate retry. The confirmation
record remains the authoritative single-use control; CloudWatch audit logging is
best-effort evidence rather than part of the write transaction.

Lambda uses the existing JSON application log configuration and seven-day log
retention. The feature adds no log group, database, stream or fixed monthly
service. It is deployed in closed DEV and has been verified in CloudWatch.

## Verification

Offline tests assert the exact record shape, reject unbounded context, prove
that confirmation and provider content cannot enter the record, verify Lambda
request-ID wiring and ensure a failed audit sink does not change the tool
response.

The 2026-09-09 closed-API validation produced successful records for
`diagnostico` and `listar_inventario_aws`. The observed keys matched the fixed
schema exactly. No external provider write was used for this verification.
