# Cognito DEV authorization runbook

The authentication foundation has a separate approval from the closed MCP
stack. This runbook does not open API Gateway, change Lambda concurrency, create
a user or handle a password.

## Preconditions

- `aws-remote-mcp-dev` is `CREATE_COMPLETE`;
- its API default endpoint is disabled;
- MCP Lambda reserved concurrency is zero;
- `aws-remote-mcp-auth-dev` doesn't exist;
- the selected Cognito prefix is still available;
- `auth-template.yaml` passes local and AWS template validation.

## Gated deployment

```powershell
$outputs = aws cloudformation describe-stacks `
  --stack-name aws-remote-mcp-dev `
  --region eu-west-1 `
  --query "Stacks[0].Outputs" `
  --output json | ConvertFrom-Json

$mcpResource = ($outputs | Where-Object OutputKey -eq 'DevMcpEndpoint').OutputValue

aws cloudformation deploy `
  --template-file auth-template.yaml `
  --stack-name aws-remote-mcp-auth-dev `
  --region eu-west-1 `
  --parameter-overrides `
    Environment=dev `
    CognitoDomainPrefix=aws-remote-mcp-dev-hg `
    McpResourceUri=$mcpResource `
    InspectorCallbackUrl=http://127.0.0.1:6276/oauth/callback `
  --no-fail-on-empty-changeset `
  --tags environment=dev project=aws-remote-mcp
```

No IAM capability is supplied or required. CloudFormation creates only one user
pool, one resource server, one public app client and one Cognito-hosted domain.

## Verification

Verify through CloudFormation and Cognito control-plane reads:

- all four resources are complete;
- tier is `LITE` and deletion protection is `ACTIVE`;
- self-registration is disabled;
- only software-token MFA is enabled and required;
- app client has no secret, only code flow and the exact callback;
- access-token validity is five minutes;
- only `aws-remote-mcp/use` is an allowed custom scope;
- no users exist;
- the MCP API is still disabled and Lambda concurrency is still zero.

Do not call Cost Explorer. Do not create the validation user as part of this
deployment.

## Cost boundary

Cognito Lite has no fixed project charge and includes 10,000 direct/social MAU
per month. An empty user pool has no active user. The future validation profile
allows only administrator-created users, and project policy permits one.

The template excludes SMS, email OTP, M2M tokens, custom domains, Lambda
triggers, WAF and paid threat protection. AWS Budgets remains a warning rather
than a guaranteed spending cap.

## Rollback and retention

The user pool has deletion protection and `Retain` policies. Deleting the stack
would intentionally retain the pool rather than remove identity data. A complete
removal requires a separate destructive authorization to:

1. delete or retain the surrounding stack resources;
2. deactivate user-pool deletion protection;
3. delete the retained user pool.

Before any user exists, a failed create may still need manual cleanup if Cognito
deletion protection prevents automatic rollback. The domain availability check
reduces the most likely create-time conflict.
