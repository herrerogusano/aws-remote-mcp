"""Tests for exhaustive, allowlisted CloudFormation project inventory."""

from __future__ import annotations

from typing import Any, cast

import pytest

from aws_remote_mcp.adapters.aws_inventory import (
    PROJECT_INVENTORY_OPERATION,
    PROJECT_STACKS,
    AwsInventoryAdapter,
)
from aws_remote_mcp.adapters.protocols import AdapterError


class FakeCloudFormationClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    def list_stack_resources(self, **kwargs: str) -> dict[str, Any]:
        self.calls.append(kwargs)
        stack = kwargs["StackName"]
        token = kwargs.get("NextToken")
        if token is None:
            return {
                "StackResourceSummaries": [
                    {
                        "LogicalResourceId": "Function",
                        "ResourceType": "AWS::Lambda::Function",
                        "PhysicalResourceId": (
                            "arn:aws:lambda:eu-west-1:123456789012:function:"
                            f"{stack}-function"
                        ),
                        "ResourceStatus": "CREATE_COMPLETE",
                    }
                ],
                "NextToken": f"next-{stack}",
            }
        return {
            "StackResourceSummaries": [
                {
                    "LogicalResourceId": "Api",
                    "ResourceType": "AWS::ApiGatewayV2::Api",
                    "PhysicalResourceId": "api-123456789012",
                    "ResourceStatus": "UPDATE_COMPLETE",
                }
            ]
        }


def resource(logical_id: str = "Function") -> dict[str, str]:
    return {
        "LogicalResourceId": logical_id,
        "ResourceType": "AWS::Lambda::Function",
        "PhysicalResourceId": "arn:aws:lambda:eu-west-1:123456789012:function:safe",
        "ResourceStatus": "CREATE_COMPLETE",
    }


def test_project_inventory_follows_every_stack_page_and_sanitizes_ids() -> None:
    client = FakeCloudFormationClient()

    def factory(service: str, region: str) -> Any:
        assert service == "cloudformation"
        assert region == "eu-west-1"
        return client

    result = AwsInventoryAdapter(region="eu-west-1", client_factory=factory).execute(
        PROJECT_INVENTORY_OPERATION, {}
    )

    assert result.status == "ok"
    assert result.sdk_requests == 8
    assert result.resources == 8
    assert result.data["complete"] is True
    assert result.data["total"] == 8
    assert result.data["writes"] == 0
    assert [call["StackName"] for call in client.calls] == [
        stack for stack in PROJECT_STACKS for _ in range(2)
    ]
    assert "123456789012" not in str(result.data)
    assert "arn:" not in str(result.data)
    resources = cast("list[dict[str, Any]]", result.data["resources"])
    assert all(
        set(resource)
        == {
            "stack",
            "logical_id",
            "resource_type",
            "physical_id",
            "status",
        }
        for resource in resources
    )


def test_project_inventory_rejects_arguments_before_client_creation() -> None:
    client = FakeCloudFormationClient()
    adapter = AwsInventoryAdapter(
        region="eu-west-1", client_factory=lambda service, region: client
    )

    with pytest.raises(AdapterError, match="does not accept arguments"):
        adapter.execute(PROJECT_INVENTORY_OPERATION, {"stack": "other"})
    assert client.calls == []


def test_project_inventory_never_claims_complete_at_page_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "aws_remote_mcp.adapters.aws_inventory.MAX_PROJECT_INVENTORY_PAGES", 1
    )
    client = FakeCloudFormationClient()
    result = AwsInventoryAdapter(
        region="eu-west-1", client_factory=lambda service, region: client
    ).execute(PROJECT_INVENTORY_OPERATION, {})

    assert result.status == "partial"
    assert result.data["complete"] is False
    assert result.issues[0].code == "project_inventory_page_limit"
    assert result.sdk_requests == len(PROJECT_STACKS)


def test_project_inventory_never_claims_complete_at_resource_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "aws_remote_mcp.adapters.aws_inventory.MAX_PROJECT_INVENTORY_RESOURCES", 1
    )
    client = FakeCloudFormationClient()
    result = AwsInventoryAdapter(
        region="eu-west-1", client_factory=lambda service, region: client
    ).execute(PROJECT_INVENTORY_OPERATION, {})

    assert result.status == "partial"
    assert result.data["complete"] is False
    assert result.data["total"] == 1
    assert result.sdk_requests == 1


def test_project_inventory_sanitizes_client_creation_failure() -> None:
    def unavailable(service: str, region: str) -> Any:
        raise RuntimeError("account=123456789012 secret=must-not-leak")

    result = AwsInventoryAdapter(
        region="eu-west-1", client_factory=unavailable
    ).execute(PROJECT_INVENTORY_OPERATION, {})

    assert result.status == "error"
    assert result.sdk_requests == 0
    assert result.data["complete"] is False
    assert result.issues[0].code == "project_inventory_client_unavailable"
    assert "must-not-leak" not in str(result)
    assert "123456789012" not in str(result)


@pytest.mark.parametrize("response", [{}, {"StackResourceSummaries": None}])
def test_project_inventory_rejects_malformed_responses(
    response: dict[str, object],
) -> None:
    class MalformedClient:
        def list_stack_resources(self, **kwargs: str) -> dict[str, object]:
            return response

    result = AwsInventoryAdapter(
        region="eu-west-1",
        client_factory=lambda service, region: MalformedClient(),
    ).execute(PROJECT_INVENTORY_OPERATION, {})

    assert result.status == "error"
    assert result.data["complete"] is False
    assert {issue.code for issue in result.issues} == {
        "project_inventory_invalid_response"
    }


def test_project_inventory_rejects_invalid_or_repeated_tokens() -> None:
    class InvalidTokenClient:
        def __init__(self) -> None:
            self.calls = 0

        def list_stack_resources(self, **kwargs: str) -> dict[str, object]:
            self.calls += 1
            if self.calls % 2:
                return {"StackResourceSummaries": [], "NextToken": "repeat"}
            return {"StackResourceSummaries": [], "NextToken": "repeat"}

    client = InvalidTokenClient()
    result = AwsInventoryAdapter(
        region="eu-west-1", client_factory=lambda service, region: client
    ).execute(PROJECT_INVENTORY_OPERATION, {})

    assert result.status == "error"
    assert result.data["complete"] is False
    assert {issue.code for issue in result.issues} == {
        "project_inventory_repeated_token"
    }
    assert result.sdk_requests == len(PROJECT_STACKS) * 2

    class NonStringTokenClient:
        def list_stack_resources(self, **kwargs: str) -> dict[str, object]:
            return {"StackResourceSummaries": [], "NextToken": 7}

    invalid = AwsInventoryAdapter(
        region="eu-west-1",
        client_factory=lambda service, region: NonStringTokenClient(),
    ).execute(PROJECT_INVENTORY_OPERATION, {})
    assert invalid.status == "error"
    assert invalid.data["complete"] is False
    assert invalid.issues[0].code == "project_inventory_invalid_token"


def test_project_inventory_omits_duplicates_and_marks_result_partial() -> None:
    class DuplicateClient:
        def list_stack_resources(self, **kwargs: str) -> dict[str, object]:
            if "NextToken" not in kwargs:
                return {
                    "StackResourceSummaries": [resource()],
                    "NextToken": "second",
                }
            return {"StackResourceSummaries": [resource()]}

    result = AwsInventoryAdapter(
        region="eu-west-1",
        client_factory=lambda service, region: DuplicateClient(),
    ).execute(PROJECT_INVENTORY_OPERATION, {})

    assert result.status == "partial"
    assert result.data["complete"] is False
    assert result.data["total"] == len(PROJECT_STACKS)
    assert {issue.code for issue in result.issues} == {
        "project_inventory_duplicate_resource"
    }
