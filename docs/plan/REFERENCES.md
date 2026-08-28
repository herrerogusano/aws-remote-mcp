# Authoritative references

Codex must verify current versions/pages when implementing.

## MCP

- Specification: https://modelcontextprotocol.io/specification/
- Official Python SDK: https://github.com/modelcontextprotocol/python-sdk

Planning assumptions to re-check:

- Streamable HTTP is the standard remote transport.
- Legacy HTTP+SSE is not the basis for new implementation.
- HTTP authorization uses OAuth/OIDC bearer-token concepts and protected-resource metadata.
- Stateless/JSON-response operation should be evaluated for serverless compatibility.

Do not freeze protocol revision numbers from this file.

## AWS

- API Gateway HTTP APIs: https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api.html
- JWT authorizers: https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-jwt-authorizer.html
- HTTP API throttling: https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-throttling.html
- Lambda + API Gateway: https://docs.aws.amazon.com/lambda/latest/dg/services-apigateway.html
- Cognito: https://docs.aws.amazon.com/cognito/latest/developerguide/cognito-user-pools.html
- SAM: https://docs.aws.amazon.com/serverless-application-model/
- Pricing: use current official service pricing pages at each gate.

## External APIs

- Telegram Bot API: https://core.telegram.org/bots/api
- Trello developer docs: https://developer.atlassian.com/cloud/trello/

Verify current Trello authentication recommendations before storing credentials.

## GitHub/AWS OIDC

Use current official GitHub Actions and AWS documentation when Phase 12 is reached.
