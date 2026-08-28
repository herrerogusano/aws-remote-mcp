# Architecture baseline

## Target runtime

```text
MCP client
  -> HTTPS / Streamable HTTP
  -> API Gateway HTTP API with JWT authorization and throttling
  -> AWS Lambda
  -> transport-independent tool services
  -> AWS APIs / Telegram / Trello
```

No runtime infrastructure exists in Phase 0. Lambda and API Gateway remain the
target unless Phase 2 proves that current MCP protocol behavior is incompatible;
changing compute would require Gate J.

## Delivery model

```text
phase branch -> pull request -> develop -> DEV
develop -> promotion pull request -> main -> PROD
```

CI starts without live integrations. CD is deferred until manual DEV and PROD
releases are stable and Gate H is approved.

## Boundaries carried forward from Exercise 2

Exercise 2 is a design reference, not a package dependency. Later phases will
adapt its central AWS operation registry, normalized results, cost classifications,
scoped consent, request counters, partial failures, and safe error translation.

The remote design adds distinct caller authorization, Lambda IAM, downstream
credentials, per-tool structured audit records, and API Gateway throttling.
