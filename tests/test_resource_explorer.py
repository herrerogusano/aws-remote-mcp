"""Offline safety and bounds tests for Resource Explorer search."""

from __future__ import annotations

from typing import Any

import pytest

from aws_remote_mcp.adapters.aws_inventory import AwsInventoryAdapter
from aws_remote_mcp.adapters.protocols import AdapterError

RESOURCE_EXPLORER_OPERATION = "aws.resource_explorer.search"
VIEW_ARN = "arn:aws:resource-explorer-2:eu-west-1:123456789012:view/test-view/abc"
QUERY = "service:lambda region:eu-west-1"


class FakeResourceExplorerClient:
    def __init__(
        self,
        *,
        response: dict[str, Any] | None = None,
        failure: Exception | None = None,
    ) -> None:
        self.response = {"Resources": []} if response is None else response
        self.failure = failure
        self.calls: list[dict[str, Any]] = []

    def search(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        if self.failure is not None:
            raise self.failure
        return self.response


def build_adapter(
    *,
    client: FakeResourceExplorerClient | None = None,
    view_arn: str | None = VIEW_ARN,
) -> tuple[AwsInventoryAdapter, FakeResourceExplorerClient, list[tuple[str, str]]]:
    client = client or FakeResourceExplorerClient()
    created: list[tuple[str, str]] = []

    def client_factory(service: str, region: str) -> FakeResourceExplorerClient:
        created.append((service, region))
        return client

    adapter = AwsInventoryAdapter(
        region="eu-west-1",
        client_factory=client_factory,
        resource_explorer_view_arn=view_arn,
    )
    return adapter, client, created


def resource(
    *,
    arn: str = "arn:aws:lambda:eu-west-1:123456789012:function:private-function",
    region: str = "eu-west-1",
    resource_type: str = "lambda:function",
) -> dict[str, Any]:
    return {
        "Arn": arn,
        "Service": "lambda",
        "Region": region,
        "ResourceType": resource_type,
        "OwningAccountId": "123456789012",
        "Properties": [
            {"Name": "Environment", "Data": '{"TOKEN":"property-secret"}'},
            {"Name": "Tags", "Data": "private-tag-value"},
        ],
    }


def test_search_uses_one_bounded_sdk_request_and_sanitizes_resource_ids() -> None:
    raw_arn = "arn:aws:lambda:eu-west-1:123456789012:function:private-function"
    client = FakeResourceExplorerClient(
        response={
            "Resources": [resource(arn=raw_arn)],
            "NextToken": "opaque-pagination-secret",
        }
    )
    adapter, client, created = build_adapter(client=client)

    result = adapter.execute(RESOURCE_EXPLORER_OPERATION, {"query": QUERY, "limit": 1})

    assert result.status == "ok"
    assert result.sdk_requests == 1
    assert result.resources == 1
    assert created == [("resource-explorer-2", "eu-west-1")]
    assert len(client.calls) == 1
    assert client.calls[0] == {
        "ViewArn": VIEW_ARN,
        "QueryString": QUERY,
        "MaxResults": 1,
    }
    assert result.data == {
        "region": "eu-west-1",
        "query": QUERY,
        "read_only": True,
        "max_results": 1,
        "returned": 1,
        "truncated": True,
        "resources": [
            {
                "service": "lambda",
                "resource_type": "lambda:function",
                "region": "eu-west-1",
                "resource_id": "function:private-function",
            }
        ],
    }
    serialized = str(result)
    for secret in (
        "123456789012",
        raw_arn,
        "opaque-pagination-secret",
        "property-secret",
        "private-tag-value",
        VIEW_ARN,
    ):
        assert secret not in serialized


def test_search_uses_default_query_and_limit() -> None:
    client = FakeResourceExplorerClient()
    adapter, client, _ = build_adapter(client=client)

    result = adapter.execute(RESOURCE_EXPLORER_OPERATION, {"query": "*", "limit": 25})

    assert result.status == "ok"
    assert result.data["query"] == "*"
    assert result.data["max_results"] == 25
    assert client.calls == [{"ViewArn": VIEW_ARN, "QueryString": "*", "MaxResults": 25}]


def test_query_whitespace_is_normalized_before_sdk_search() -> None:
    client = FakeResourceExplorerClient()
    adapter, client, _ = build_adapter(client=client)
    spaced_query = "  service:lambda   region:eu-west-1  "

    result = adapter.execute(
        RESOURCE_EXPLORER_OPERATION, {"query": spaced_query, "limit": 4}
    )

    assert result.status == "ok"
    assert result.data["query"] == QUERY
    assert client.calls == [
        {"ViewArn": VIEW_ARN, "QueryString": QUERY, "MaxResults": 4}
    ]


@pytest.mark.parametrize(
    "query",
    [
        "",
        "  \t",
        "x" * 257,
        "SERVICE:lambda",
        "service :lambda",
        "service:lambda:extra",
        "service:lambda OR service:s3",
        "NOT service:lambda",
        "-service:lambda",
        "accountid:123456789012",
        "id:private-resource",
        "tag:Name=private",
        'service:"lambda"',
        "service:lambda\x00 region:eu-west-1",
    ],
)
def test_unsafe_or_invalid_query_fails_before_client_creation(query: str) -> None:
    adapter, client, created = build_adapter()

    with pytest.raises(AdapterError):
        adapter.execute(RESOURCE_EXPLORER_OPERATION, {"query": query, "limit": 25})

    assert created == []
    assert client.calls == []


@pytest.mark.parametrize(
    ("arguments"),
    [
        {"query": ["service:lambda"]},
        {"query": None},
        {"query": "*", "limit": 0},
        {"query": "*", "limit": 51},
        {"query": "*", "limit": True},
        {"query": "*", "limit": 1.5},
        {"query": "*", "limit": "10"},
        {"query": "*", "limit": 10, "next_token": "attacker-token"},
    ],
)
def test_invalid_search_arguments_fail_before_client_creation(
    arguments: dict[str, Any],
) -> None:
    adapter, client, created = build_adapter()

    with pytest.raises(AdapterError):
        adapter.execute(RESOURCE_EXPLORER_OPERATION, arguments)

    assert created == []
    assert client.calls == []


@pytest.mark.parametrize("limit", [1, 25, 50])
def test_search_accepts_limits_within_the_configured_bound(limit: int) -> None:
    client = FakeResourceExplorerClient()
    adapter, client, _ = build_adapter(client=client)

    result = adapter.execute(
        RESOURCE_EXPLORER_OPERATION, {"query": "*", "limit": limit}
    )

    assert result.status == "ok"
    assert client.calls[0]["MaxResults"] == limit


@pytest.mark.parametrize("view_arn", [None, "not-an-arn"])
def test_view_arn_is_required_and_fails_closed_before_client_creation(
    view_arn: str | None,
) -> None:
    adapter, client, created = build_adapter(view_arn=view_arn)

    result = adapter.execute(RESOURCE_EXPLORER_OPERATION, {"query": QUERY, "limit": 5})

    assert result.status == "error"
    assert result.sdk_requests == 0
    assert result.resources == 0
    assert created == []
    assert client.calls == []
    assert "ViewArn" not in str(result.data)


def test_malformed_resources_are_omitted_with_one_sanitized_partial_issue() -> None:
    malformed_arn = "arn:aws:lambda:eu-west-1:999999999999"
    client = FakeResourceExplorerClient(
        response={
            "Resources": [resource(), resource(arn=malformed_arn), {"Arn": "bad"}]
        }
    )
    adapter, client, _ = build_adapter(client=client)

    result = adapter.execute(RESOURCE_EXPLORER_OPERATION, {"query": QUERY, "limit": 10})

    assert result.status == "partial"
    assert result.sdk_requests == 1
    assert result.resources == 1
    assert len(result.issues) == 1
    assert result.issues[0].code == "resource_explorer_invalid_resources"
    assert "999999999999" not in str(result)
    assert "arn:aws:lambda:eu-west-1:999999999999" not in str(result)
    assert len(client.calls) == 1


def test_all_malformed_resources_return_error_without_raw_provider_data() -> None:
    client = FakeResourceExplorerClient(
        response={"Resources": [{"Arn": "arn:aws:lambda:eu-west-1:999999999999"}]}
    )
    adapter, _, _ = build_adapter(client=client)

    result = adapter.execute(RESOURCE_EXPLORER_OPERATION, {"query": QUERY, "limit": 1})

    assert result.status == "error"
    assert result.sdk_requests == 1
    assert result.resources == 0
    assert len(result.issues) == 1
    assert "999999999999" not in str(result)


def test_long_resource_id_is_truncated() -> None:
    long_resource_id = f"function:{'x' * 200}"
    client = FakeResourceExplorerClient(
        response={
            "Resources": [
                resource(
                    arn=f"arn:aws:lambda:eu-west-1:123456789012:{long_resource_id}"
                )
            ]
        }
    )
    adapter, _, _ = build_adapter(client=client)

    result = adapter.execute(RESOURCE_EXPLORER_OPERATION, {"query": QUERY, "limit": 1})

    resources = result.data["resources"]
    assert isinstance(resources, list)
    assert result.status == "ok"
    assert len(resources) == 1
    assert isinstance(resources[0], dict)
    resource_id = resources[0]["resource_id"]
    assert isinstance(resource_id, str)
    assert len(resource_id) == 128


def test_excess_resources_are_clipped_and_marked_truncated_without_next_page() -> None:
    client = FakeResourceExplorerClient(
        response={
            "Resources": [
                resource(),
                resource(arn="arn:aws:lambda:eu-west-1:123456789012:function:second"),
            ]
        }
    )
    adapter, client, _ = build_adapter(client=client)

    result = adapter.execute(RESOURCE_EXPLORER_OPERATION, {"query": QUERY, "limit": 1})

    assert result.status == "ok"
    assert result.sdk_requests == 1
    assert result.resources == 1
    assert result.data["returned"] == 1
    assert result.data["truncated"] is True
    returned_resources = result.data["resources"]
    assert isinstance(returned_resources, list)
    assert len(returned_resources) == 1
    assert len(client.calls) == 1


@pytest.mark.parametrize(
    "response",
    [{}, {"Resources": None}, {"Resources": "not-a-list"}],
)
def test_invalid_top_level_resources_response_returns_sanitized_error(
    response: dict[str, Any],
) -> None:
    adapter, _, _ = build_adapter(client=FakeResourceExplorerClient(response=response))

    result = adapter.execute(RESOURCE_EXPLORER_OPERATION, {"query": QUERY, "limit": 10})

    assert result.status == "error"
    assert result.sdk_requests == 1
    assert result.resources == 0
    assert len(result.issues) == 1
    assert "Resources" not in str(result.issues[0].message)


def test_sdk_exception_is_sanitized_and_counted_once() -> None:
    raw = RuntimeError("account=123456789012 token=provider-secret")
    adapter, _, created = build_adapter(client=FakeResourceExplorerClient(failure=raw))

    result = adapter.execute(RESOURCE_EXPLORER_OPERATION, {"query": QUERY, "limit": 10})

    assert result.status == "error"
    assert result.sdk_requests == 1
    assert result.resources == 0
    assert len(result.issues) == 1
    assert "provider-secret" not in str(result)
    assert "123456789012" not in str(result)
    assert created == [("resource-explorer-2", "eu-west-1")]
