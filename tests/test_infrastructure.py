"""Static safety regressions for the pre-deployment SAM template."""

from pathlib import Path

TEMPLATE = Path(__file__).parents[1] / "template.yaml"


def template_text() -> str:
    return TEMPLATE.read_text(encoding="utf-8")


def test_template_is_dev_only_and_bounded() -> None:
    template = template_text()

    assert "AllowedValues:\n      - dev" in template
    assert "Runtime: python3.13" in template
    assert "MemorySize: 256" in template
    assert "Timeout: 15" in template
    assert "ReservedConcurrentExecutions: 2" in template
    assert "ThrottlingBurstLimit: 2" in template
    assert "ThrottlingRateLimit: 1" in template
    assert template.count("RetentionInDays: 7") == 2


def test_template_iam_is_exactly_log_delivery() -> None:
    template = template_text()

    assert "logs:CreateLogStream" in template
    assert "logs:PutLogEvents" in template
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
    assert "Method: GET" not in template
