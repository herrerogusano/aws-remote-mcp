"""Static safety regressions for the pre-deployment SAM template."""

from pathlib import Path

TEMPLATE = Path(__file__).parents[1] / "template.yaml"


def template_text() -> str:
    return TEMPLATE.read_text(encoding="utf-8")


def test_template_is_dev_only_and_bounded() -> None:
    template = template_text()

    assert "AllowedValues:\n      - dev" in template
    assert "Runtime: python3.13" in template
    assert "MemorySize: 128" in template
    assert "Timeout: 10" in template
    assert "ReservedConcurrentExecutions: 0" in template
    assert template.count("ReservedConcurrentExecutions:") == 1
    assert "ThrottlingBurstLimit: 1" in template
    assert "ThrottlingRateLimit: 1" in template
    assert 'StageName: "$default"' in template
    assert "DevStageName:" in template
    assert template.count("RetentionInDays: 7") == 3


def test_endpoint_is_closed_and_jwt_authenticated_by_default() -> None:
    template = template_text()

    assert "DisableExecuteApiEndpoint: true" in template
    assert "FailOnWarnings: true" in template
    assert 'openapi: "3.0.1"' in template
    assert 'url: "/"' in template
    assert "paths: {}" in template
    assert "CognitoJwtAuthorizer:" in template
    assert "DefaultAuthorizer: CognitoJwtAuthorizer" in template
    assert 'IdentitySource: "$request.header.Authorization"' in template
    assert "issuer: !Ref CognitoIssuer" in template
    assert "- !Ref McpTokenAudience" in template
    assert "AuthorizationScopes:" in template
    assert "- aws-remote-mcp/use" in template
    assert "EnableIamAuthorizer" not in template
    assert "AWS_IAM" not in template


def test_template_iam_is_exactly_log_delivery() -> None:
    template = template_text()

    assert "logs:CreateLogStream" in template
    assert "logs:PutLogEvents" in template
    assert "apigateway:PATCH" in template
    assert "lambda:PutFunctionConcurrency" in template
    assert "cloudwatch:DeleteAlarms" in template
    assert "lambda:InvokeFunction" in template
    assert 'Action: "*"' not in template
    assert "AdministratorAccess" not in template
    assert "PowerUserAccess" not in template
    assert "ReadOnlyAccess" not in template


def test_template_has_no_expensive_or_persistent_extras() -> None:
    template = template_text()

    for forbidden in (
        "VpcConfig",
        "ProvisionedConcurrency",
        "AWS::EC2::NatGateway",
        "AWS::WAF",
        "AWS::Route53",
        "AWS::DynamoDB",
        "AWS::SQS",
    ):
        assert forbidden not in template


def test_only_current_mcp_post_route_is_exposed() -> None:
    template = template_text()

    assert "Method: POST" in template
    assert "Path: /mcp" in template
    assert 'PayloadFormatVersion: "2.0"' in template
    assert "Method: ANY" not in template
    assert template.count("Method: GET") == 1
    assert template.count("Method: OPTIONS") == 1
    assert template.count("Path: /.well-known/oauth-protected-resource/mcp") == 2
    assert template.count("Authorizer: NONE") == 2


def test_automatic_shutdown_is_wired_to_exact_resources() -> None:
    template = template_text()

    assert "SafetyShutdownFunction:" in template
    assert "SafetyShutdownTopic:" in template
    assert "SafetyShutdownScheduleGroup:" in template
    assert "Service: scheduler.amazonaws.com" in template
    assert "Service: cloudwatch.amazonaws.com" in template
    assert "aws-remote-mcp-${Environment}-request-kill-switch" in template
    assert "close-only-this-dev-endpoint" in template
    assert "aws:SourceArn: !GetAtt SafetyShutdownScheduleGroup.Arn" in template
