"""Foundation smoke tests that require no network or cloud access."""

from aws_remote_mcp import PROJECT_NAME


def test_package_imports() -> None:
    assert PROJECT_NAME == "aws-remote-mcp"
