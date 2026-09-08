# Confirmed Telegram and Trello actions

## State

The implementation and conditional infrastructure are prepared and tested
offline. They are not enabled in AWS, no provider credential exists in the
project, and no external message or card has been created by this milestone.

`EnableExternalIntegrations=false` is the deployment default. Enabling it adds:

- one DynamoDB on-demand confirmation table with 1 RRU/s and 1 WRU/s maximums;
- exact `PutItem`, `UpdateItem` and `GetItem` access to that table;
- exact `GetParameter` access to one DEV Parameter Store path;
- prepare and execute MCP tools for Telegram and Trello.

The HTTP API, Lambda concurrency, five-minute window and shutdown controls do
not change.

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

The exact parameter is a Standard `SecureString`, no larger than 4 KiB, under
`/aws-remote-mcp/dev/`. Its JSON shape is:

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

Provider setup and AWS activation are deliberately separate:

1. Create or select a Telegram bot and exact destination.
2. Create a Trello token limited to the shortest practical expiry and required
   write scope, then identify one exact list.
3. Create the Standard SecureString and verify only its type, tier, name and ARN.
4. Deploy with `EnableExternalIntegrations=true` while the endpoint and Lambda
   remain closed, then audit the table limits and exact IAM resources.
5. Open one bounded DEV window and separately confirm one harmless Telegram
   message and one disposable Trello card.
6. Close and independently verify every shutdown invariant.

Steps 1-4 change external or AWS state and require an impact review. Step 5
creates visible external content and requires a new explicit confirmation.

## Primary references

- https://core.telegram.org/bots/api#sendmessage
- https://developer.atlassian.com/cloud/trello/rest/api-group-cards/#api-cards-post
- https://developer.atlassian.com/cloud/trello/guides/rest-api/authorization/
- https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/on-demand-capacity-mode-max-throughput.html
- https://aws.amazon.com/systems-manager/pricing/
