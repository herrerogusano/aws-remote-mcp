"""Static safety regressions for the gated Cognito OAuth template."""

from pathlib import Path

TEMPLATE = Path(__file__).parents[1] / "auth-template.yaml"


def template_text() -> str:
    return TEMPLATE.read_text(encoding="utf-8")


def test_auth_template_is_dev_only_and_not_implicitly_deployable() -> None:
    template = template_text()

    assert "AllowedValues:\n      - dev" in template
    assert "CognitoDomainPrefix:" in template
    assert "^(?!.*(?:aws|amazon|cognito))" in template
    assert "McpResourceUri:" in template
    assert "TotpEnrollmentEnabled:" in template
    assert 'Default: "false"' in template
    assert (
        'TotpEnrollmentActive: !Equals [!Ref TotpEnrollmentEnabled, "true"]' in template
    )
    assert "Default: dev" in template
    assert "Default: https://" not in template
    assert "Default: aws-remote-mcp" not in template
    assert "CognitoDomainPrefix=aws-remote-mcp" not in template


def test_user_pool_prevents_unbounded_sign_up_and_enforces_threat_protection() -> None:
    template = template_text()

    assert "UserPoolTier: PLUS" in template
    assert "DeletionProtection: ACTIVE" in template
    assert "AdvancedSecurityMode: ENFORCED" in template
    assert "DeletionPolicy: Retain" in template
    assert "AllowAdminCreateUserOnly: true" in template
    assert 'MfaConfiguration: "ON"' in template
    assert "SOFTWARE_TOKEN_MFA" in template
    assert "SMS_MFA" not in template
    assert "EMAIL_OTP" not in template
    assert "CustomDomainConfig" not in template


def test_inspector_client_is_public_pkce_only_and_short_lived() -> None:
    template = template_text()

    assert "GenerateSecret: false" in template
    assert "PreventUserExistenceErrors: ENABLED" in template
    assert "AllowedOAuthFlows:\n        - code" in template
    assert "client_credentials" not in template
    assert "implicit" not in template
    assert "aws-remote-mcp/use" in template
    assert "aws.cognito.signin.user.admin" in template
    assert "TotpEnrollmentActive" in template
    assert "TotpEnrollmentGate:" in template
    assert "Value: !Ref TotpEnrollmentEnabled" in template
    assert "http://127.0.0.1:6276/oauth/callback" in template
    assert "AccessTokenValidity: 5" in template
    assert "RefreshTokenValidity: 1" in template
    assert "EnableTokenRevocation: true" in template
    assert "ExplicitAuthFlows: []" in template
    assert "ALLOW_" not in template
    assert "RefreshTokenRotation" in template
    assert "Feature: ENABLED" in template
    assert "RetryGracePeriodSeconds: 0" in template
    assert "ManagedLoginVersion: 2" in template
    assert "AWS::Cognito::ManagedLoginBranding" in template
    assert "UseCognitoProvidedValues: true" in template
    assert "InspectorManagedLoginBranding" in template


def test_auth_template_has_only_the_expected_resources() -> None:
    template = template_text()

    assert template.count("    Type: AWS::") == 5
    assert "AWS::Cognito::UserPool\n" in template
    assert "AWS::Cognito::UserPoolClient" in template
    assert "AWS::Cognito::UserPoolResourceServer" in template
    assert "AWS::Cognito::UserPoolDomain" in template
    assert "AWS::Cognito::ManagedLoginBranding" in template
    for forbidden in ("AWS::Lambda", "AWS::WAF", "AWS::Route53", "AWS::SNS"):
        assert forbidden not in template
