# Confirmed Telegram and Trello actions

## State

The implementation and conditional infrastructure are deployed in DEV while
the public endpoint and Lambda execution remain closed. Provider configuration
is stored in one Standard SecureString; no provider credential exists in the
repository, deployment parameters, outputs or logs. One harmless Telegram
message and one disposable Trello card completed the closed-API DEV validation.

`EnableExternalIntegrations=false` remains the template default. The explicitly
approved DEV deployment currently enables:

- one DynamoDB on-demand confirmation table with 1 RRU/s and 1 WRU/s maximums;
- exact `PutItem`, `UpdateItem` and `GetItem` access to that table;
- exact `GetParameter` access to one DEV Parameter Store path;
- prepare and execute MCP tools for Telegram and Trello.

The HTTP API, Lambda concurrency, five-minute window and shutdown controls do
not change.

## Provider credential posture

The Telegram bot accepts only the configured private `owner` destination and
group joining is disabled at the provider. The runtime never accepts a raw chat
identifier from callers.

Trello's delegated token cannot be restricted by the provider to one board or
list. The operational token is therefore long-lived for unattended service, but
the runtime maps callers only to the fixed `portfolio/inbox` alias and its exact
list identifier. The token has no account-management scope. A suspected
disclosure requires immediate provider revocation and replacement of the
SecureString value; changing only the application allowlist is not sufficient.

## Confirmation lifecycle

1. A prepare tool validates an allowlisted alias and bounded content.
2. It stores a token digest, caller fingerprint, action, payload digest, expiry
   and `consumed=false`; the plaintext token is returned only to the caller.
3. The execute tool repeats validation and atomically sets `consumed=true` only
   when every bound value matches and the record has not expired.
4. Only after that update succeeds does the adapter load credentials and make
   one provider request.
5. Success, rejection or an ambiguous timeout never retries the provider write.

This ordering prefers a missed write over a duplicate message or card.

## SecureString contract

The exact parameter is a Standard `SecureString`, no larger than 4 KiB, at
`/portfolio/aws-remote-mcp/dev/integrations`. Its JSON shape is:

```json
{
  "telegram": {
    "bot_token": "REPLACE_AT_PROVISIONING_TIME",
    "destinations": {
      "owner": "REPLACE_AT_PROVISIONING_TIME"
    }
  },
  "trello": {
    "api_key": "REPLACE_AT_PROVISIONING_TIME",
    "api_token": "REPLACE_AT_PROVISIONING_TIME",
    "destinations": [
      {
        "board": "portfolio",
        "list": "inbox",
        "list_id": "REPLACE_AT_PROVISIONING_TIME"
      }
    ]
  }
}
```

Never place the real JSON in a shell history, deployment parameter, repository,
CloudFormation output or log. Provisioning must use a local temporary file or an
interactive input path that is deleted immediately afterward, and verification
must inspect metadata only.

## Next gated operations

Provider setup and AWS activation remain operationally separate:

1. Completed: create the Telegram bot and exact private destination.
2. Completed: authorize Trello and resolve one exact `MCP Inbox` list.
3. Completed: create the Standard SecureString and verify metadata only.
4. Completed: deploy with `EnableExternalIntegrations=true` while closed and
   audit table limits, encryption, TTL, IAM and shutdown invariants.
5. Completed: validate one harmless Telegram message and one disposable Trello
   card by direct Lambda invocation while API Gateway remained disabled.
6. Completed: restore Lambda concurrency to zero and independently verify no
   alarm or automatic-close schedule remained.
6. Close and independently verify every shutdown invariant.

Any additional visible external content requires a new explicit confirmation.

## Primary references

- https://core.telegram.org/bots/api#sendmessage
- https://developer.atlassian.com/cloud/trello/rest/api-group-cards/#api-cards-post
- https://developer.atlassian.com/cloud/trello/guides/rest-api/authorization/
- https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/on-demand-capacity-mode-max-throughput.html
- https://aws.amazon.com/systems-manager/pricing/
