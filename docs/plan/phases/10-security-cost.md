# Phase 10 — Security and cost hardening

## Goal
Perform a dedicated audit before treating the remote MCP as production-shaped.

## Threat model
Review anonymous internet traffic, stolen bearer tokens, prompt/tool misuse, argument injection, token/confirmation replay, Origin/DNS-rebinding behavior, arbitrary URLs/SSRF-like input, secret leakage, broad IAM, duplicated third-party writes and cost amplification.

## IAM
Produce an exact role/permission matrix. No `AdministratorAccess`, `PowerUserAccess`, blanket `ReadOnlyAccess`, or unjustified `Action: "*"`.

## Secrets
Audit secret storage and access. No secret values in committed CloudFormation/SAM parameters.

## AWS-call budget
Hard caps prevent unlimited regions/services/pages/resources/SDK calls.

## Side-effect budget
Per confirmed execution:
- max one Telegram send;
- max one Trello card create.

Confirmation tokens remain short-lived and single-use.

## Cost review
Create a current cost inventory for API Gateway, Lambda, CloudWatch Logs, Cognito, secret storage and every other deployed resource. Use official current pricing.

Document external Telegram/Trello limits/costs when relevant.

## CI security regression tests
Fail on:
- leaked token patterns;
- broad IAM regression;
- auth disabled on `/mcp`;
- unknown AWS operation auto-allowed;
- confirmation bypass;
- unbounded page/request caps;
- third-party write retries;
- provisioned concurrency;
- accidental expensive resources.

## Done
Security/cost posture is documented and guarded by tests where practical.
