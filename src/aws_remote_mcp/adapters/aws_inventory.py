"""Bounded AWS control-plane inventory adapter with a fixed operation allowlist."""

from __future__ import annotations

import importlib
import re
from collections.abc import Callable, Mapping
from typing import Any, Literal

from aws_remote_mcp.adapters.protocols import (
    AdapterError,
    AdapterIssue,
    AwsAdapterResult,
)
from aws_remote_mcp.core.models import JsonValue

INVENTORY_OPERATION = "aws.inventory.list"
RESOURCE_EXPLORER_OPERATION = "aws.resource_explorer.search"
PROJECT_INVENTORY_OPERATION = "aws.cloudformation.project_inventory"
MAX_RESOURCES_PER_SERVICE = 10
SUPPORTED_REGION = "eu-west-1"
MAX_NAME_CHARS = 128
MAX_RESOURCE_EXPLORER_RESULTS = 50
MAX_RESOURCE_EXPLORER_QUERY_CHARS = 256
MAX_PROJECT_INVENTORY_PAGES = 20
MAX_PROJECT_INVENTORY_RESOURCES = 100
PROJECT_STACKS = (
    "aws-remote-mcp-dev",
    "aws-remote-mcp-prod",
    "aws-remote-mcp-auth-dev",
    "aws-remote-mcp-auth-prod",
)
RESOURCE_EXPLORER_SERVICES = frozenset(
    {
        "apigateway",
        "apigatewayv2",
        "cloudformation",
        "dynamodb",
        "ec2",
        "ecs",
        "eks",
        "elasticloadbalancing",
        "iam",
        "kms",
        "lambda",
        "logs",
        "rds",
        "route53",
        "s3",
        "secretsmanager",
        "sns",
        "sqs",
        "ssm",
    }
)
_RESOURCE_EXPLORER_VIEW_ARN = re.compile(
    r"arn:aws:resource-explorer-2:eu-west-1:\d{12}:view/"
    r"[A-Za-z0-9_-]{1,64}/[A-Za-z0-9-]{1,64}\Z"
)
_RESOURCE_EXPLORER_REGION = re.compile(r"[a-z]{2}(?:-[a-z0-9]+){1,4}-\d\Z")
_RESOURCE_EXPLORER_SERVICE = re.compile(r"[a-z0-9-]{1,64}\Z")
_RESOURCE_EXPLORER_RESOURCE_TYPE = re.compile(r"([a-z0-9-]+):([a-z0-9][a-z0-9-]*)\Z")
_RESOURCE_EXPLORER_KEYWORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]*\Z")
_RESOURCE_ID_CHARS = re.compile(r"[^A-Za-z0-9._:/+=-]")

type AwsClientFactory = Callable[[str, str], Any]


def _safe_string(value: object, *, fallback: str = "unknown") -> str:
    if not isinstance(value, str) or not value:
        return fallback
    return value[:MAX_NAME_CHARS]


def _boto_client(service: str, region: str) -> Any:
    """Create a runtime SDK client only when the real inventory tool is called."""

    boto3 = importlib.import_module("boto3")
    config_module = importlib.import_module("botocore.config")
    config = config_module.Config(
        connect_timeout=2,
        read_timeout=3,
        retries={"total_max_attempts": 1, "mode": "standard"},
    )
    return boto3.client(service, region_name=region, config=config)


class AwsInventoryAdapter:
    """Execute bounded, read-only AWS inventory and Resource Explorer requests."""

    def __init__(
        self,
        *,
        region: str,
        client_factory: AwsClientFactory = _boto_client,
        max_resources_per_service: int = MAX_RESOURCES_PER_SERVICE,
        resource_explorer_view_arn: str | None = None,
    ) -> None:
        if region != SUPPORTED_REGION:
            raise ValueError(f"AWS inventory is restricted to {SUPPORTED_REGION}.")
        if not 1 <= max_resources_per_service <= MAX_RESOURCES_PER_SERVICE:
            raise ValueError(
                f"Inventory limit must be between 1 and {MAX_RESOURCES_PER_SERVICE}."
            )
        self._region = region
        self._client_factory = client_factory
        self._limit = max_resources_per_service
        self._resource_explorer_view_arn = resource_explorer_view_arn

    def execute(
        self, operation: str, arguments: Mapping[str, JsonValue]
    ) -> AwsAdapterResult:
        if operation == RESOURCE_EXPLORER_OPERATION:
            return self._search_resource_explorer(arguments)
        if operation == PROJECT_INVENTORY_OPERATION:
            return self._list_project_cloudformation_resources(arguments)
        if operation != INVENTORY_OPERATION:
            raise AdapterError(
                "aws_operation_not_supported",
                "The AWS adapter operation is not supported.",
            )
        if arguments:
            raise AdapterError(
                "invalid_inventory_arguments",
                "AWS inventory does not accept arguments.",
            )

        services: dict[str, JsonValue] = {}
        issues: list[AdapterIssue] = []
        resources = 0
        sdk_requests = 0
        successful_services = 0

        sdk_requests += 1
        try:
            lambda_resources, lambda_truncated = self._list_lambda_functions()
            services["lambda"] = {
                "status": "ok",
                "truncated": lambda_truncated,
                "resources": lambda_resources,
            }
            resources += len(lambda_resources)
            successful_services += 1
        except Exception:
            services["lambda"] = {
                "status": "unavailable",
                "truncated": False,
                "resources": [],
            }
            issues.append(
                AdapterIssue(
                    "lambda_inventory_unavailable",
                    "Lambda inventory could not be read.",
                )
            )

        sdk_requests += 1
        try:
            api_resources, api_truncated = self._list_http_apis()
            services["api_gateway_v2"] = {
                "status": "ok",
                "truncated": api_truncated,
                "resources": api_resources,
            }
            resources += len(api_resources)
            successful_services += 1
        except Exception:
            services["api_gateway_v2"] = {
                "status": "unavailable",
                "truncated": False,
                "resources": [],
            }
            issues.append(
                AdapterIssue(
                    "api_gateway_inventory_unavailable",
                    "API Gateway inventory could not be read.",
                )
            )

        status: Literal["ok", "partial", "error"] = (
            "ok"
            if successful_services == 2
            else "partial"
            if successful_services == 1
            else "error"
        )
        return AwsAdapterResult(
            data={
                "region": self._region,
                "read_only": True,
                "max_resources_per_service": self._limit,
                "services": services,
            },
            sdk_requests=sdk_requests,
            resources=resources,
            status=status,
            issues=tuple(issues),
        )

    def _list_project_cloudformation_resources(
        self, arguments: Mapping[str, JsonValue]
    ) -> AwsAdapterResult:
        """List all resources in the fixed project CloudFormation stacks.

        Stack names are intentionally not caller-controlled. Pagination is
        followed until every allowlisted stack is exhausted, subject to hard
        safety caps that can only make ``complete`` false.
        """

        if arguments:
            raise AdapterError(
                "invalid_project_inventory_arguments",
                "Project CloudFormation inventory does not accept arguments.",
            )

        resources: list[JsonValue] = []
        issues: list[AdapterIssue] = []
        issue_codes: set[str] = set()
        seen_resources: set[tuple[str, str]] = set()
        sdk_requests = 0
        complete = True

        def add_issue(code: str, message: str) -> None:
            if code not in issue_codes:
                issue_codes.add(code)
                issues.append(AdapterIssue(code, message))

        try:
            client = self._client_factory("cloudformation", self._region)
        except Exception:
            add_issue(
                "project_inventory_client_unavailable",
                "The CloudFormation inventory client could not be created.",
            )
            return _project_inventory_result(
                resources=resources,
                sdk_requests=sdk_requests,
                complete=False,
                issues=issues,
                region=self._region,
            )

        for stack in PROJECT_STACKS:
            next_token: str | None = None
            seen_tokens: set[str] = set()
            pages = 0
            stack_complete = False
            while not stack_complete:
                if pages >= MAX_PROJECT_INVENTORY_PAGES:
                    complete = False
                    add_issue(
                        "project_inventory_page_limit",
                        "Project inventory reached its defensive page limit.",
                    )
                    break

                request: dict[str, str] = {"StackName": stack}
                if next_token is not None:
                    request["NextToken"] = next_token
                sdk_requests += 1
                try:
                    response = client.list_stack_resources(**request)
                except Exception:
                    complete = False
                    add_issue(
                        "project_inventory_stack_unavailable",
                        "A project CloudFormation stack could not be read.",
                    )
                    break
                pages += 1
                if not isinstance(response, Mapping):
                    complete = False
                    add_issue(
                        "project_inventory_invalid_response",
                        "CloudFormation returned an invalid stack response.",
                    )
                    break
                if "StackResourceSummaries" not in response:
                    complete = False
                    add_issue(
                        "project_inventory_invalid_response",
                        "CloudFormation returned an incomplete stack response.",
                    )
                    break
                page_resources = response["StackResourceSummaries"]
                if not isinstance(page_resources, list):
                    complete = False
                    add_issue(
                        "project_inventory_invalid_response",
                        "CloudFormation returned an invalid resource list.",
                    )
                    break
                for item in page_resources:
                    sanitized = _sanitize_cloudformation_resource(item, stack)
                    if sanitized is None:
                        complete = False
                        add_issue(
                            "project_inventory_invalid_resource",
                            "Some CloudFormation resources were omitted because "
                            "they were malformed.",
                        )
                        continue
                    logical_id = sanitized["logical_id"]
                    if not isinstance(logical_id, str):
                        complete = False
                        add_issue(
                            "project_inventory_invalid_resource",
                            "Some CloudFormation resources were omitted because "
                            "they were malformed.",
                        )
                        continue
                    resource_key = (stack, logical_id)
                    if resource_key in seen_resources:
                        complete = False
                        add_issue(
                            "project_inventory_duplicate_resource",
                            "A duplicate CloudFormation resource was omitted.",
                        )
                        continue
                    if len(resources) >= MAX_PROJECT_INVENTORY_RESOURCES:
                        complete = False
                        break
                    seen_resources.add(resource_key)
                    resources.append(sanitized)
                if len(resources) >= MAX_PROJECT_INVENTORY_RESOURCES:
                    complete = False
                    add_issue(
                        "project_inventory_resource_limit",
                        "Project inventory reached its defensive resource limit.",
                    )
                    break

                if "NextToken" not in response:
                    stack_complete = True
                    continue
                candidate = response["NextToken"]
                if not isinstance(candidate, str) or not candidate:
                    complete = False
                    add_issue(
                        "project_inventory_invalid_token",
                        "CloudFormation returned an invalid pagination token.",
                    )
                    break
                if candidate in seen_tokens:
                    complete = False
                    add_issue(
                        "project_inventory_repeated_token",
                        "CloudFormation repeated a pagination token.",
                    )
                    break
                seen_tokens.add(candidate)
                next_token = candidate
            if len(resources) >= MAX_PROJECT_INVENTORY_RESOURCES:
                complete = False
                break

        return _project_inventory_result(
            resources=resources,
            sdk_requests=sdk_requests,
            complete=complete,
            issues=issues,
            region=self._region,
        )

    def _search_resource_explorer(
        self, arguments: Mapping[str, JsonValue]
    ) -> AwsAdapterResult:
        if not set(arguments).issubset({"query", "limit"}):
            raise AdapterError(
                "invalid_resource_explorer_arguments",
                "Resource Explorer requires a query and a result limit.",
            )
        query = arguments.get("query", "*")
        result_limit = arguments.get("limit", 25)
        if not isinstance(query, str):
            raise AdapterError(
                "invalid_resource_explorer_query",
                "Resource Explorer query is invalid.",
            )
        if (
            not isinstance(result_limit, int)
            or isinstance(result_limit, bool)
            or not 1 <= result_limit <= MAX_RESOURCE_EXPLORER_RESULTS
        ):
            raise AdapterError(
                "invalid_resource_explorer_limit",
                "Resource Explorer limit must be between 1 and 50.",
            )
        normalized_query = _validate_resource_explorer_query(query)
        view_arn = self._resource_explorer_view_arn
        if (
            not isinstance(view_arn, str)
            or _RESOURCE_EXPLORER_VIEW_ARN.fullmatch(view_arn) is None
        ):
            return _resource_explorer_failure(
                query=normalized_query,
                result_limit=result_limit,
                region=self._region,
                code="resource_explorer_view_unavailable",
                message="A valid Resource Explorer view is not configured.",
                sdk_requests=0,
            )

        try:
            client = self._client_factory("resource-explorer-2", self._region)
            response = client.search(
                QueryString=normalized_query,
                MaxResults=result_limit,
                ViewArn=view_arn,
            )
        except Exception:
            return _resource_explorer_failure(
                query=normalized_query,
                result_limit=result_limit,
                region=self._region,
                code="resource_explorer_search_unavailable",
                message="AWS Resource Explorer search could not be completed.",
                sdk_requests=1,
            )

        if not isinstance(response, Mapping):
            return _resource_explorer_failure(
                query=normalized_query,
                result_limit=result_limit,
                region=self._region,
                code="invalid_resource_explorer_response",
                message="AWS Resource Explorer returned an invalid response.",
                sdk_requests=1,
            )
        response_resources = response.get("Resources")
        if not isinstance(response_resources, list):
            return _resource_explorer_failure(
                query=normalized_query,
                result_limit=result_limit,
                region=self._region,
                code="invalid_resource_explorer_response",
                message="AWS Resource Explorer returned an invalid response.",
                sdk_requests=1,
            )

        resources: list[JsonValue] = []
        malformed_count = 0
        for item in response_resources[:result_limit]:
            sanitized = _sanitize_resource_explorer_item(item)
            if sanitized is None:
                malformed_count += 1
                continue
            resources.append(sanitized)
        has_next_page = isinstance(response.get("NextToken"), str) and bool(
            response.get("NextToken")
        )
        issues = (
            (
                AdapterIssue(
                    "resource_explorer_invalid_resources",
                    "Some Resource Explorer results were omitted because "
                    "they were malformed.",
                ),
            )
            if malformed_count
            else ()
        )
        status: Literal["ok", "partial", "error"] = (
            "partial"
            if malformed_count and resources
            else "error"
            if malformed_count
            else "ok"
        )
        return AwsAdapterResult(
            data={
                "region": self._region,
                "query": normalized_query,
                "max_results": result_limit,
                "read_only": True,
                "returned": len(resources),
                "truncated": has_next_page or len(response_resources) > result_limit,
                "resources": resources,
            },
            sdk_requests=1,
            resources=len(resources),
            status=status,
            issues=issues,
        )

    def _list_lambda_functions(self) -> tuple[list[JsonValue], bool]:
        client = self._client_factory("lambda", self._region)
        response = client.list_functions(MaxItems=self._limit)
        functions = response.get("Functions", [])
        if not isinstance(functions, list):
            raise TypeError("Invalid Lambda inventory response.")
        resources: list[JsonValue] = []
        for item in functions[: self._limit]:
            if not isinstance(item, dict):
                continue
            architectures = item.get("Architectures", [])
            architecture = (
                architectures[0]
                if isinstance(architectures, list) and architectures
                else "unknown"
            )
            resources.append(
                {
                    "service": "lambda",
                    "resource_type": "AWS::Lambda::Function",
                    "name": _safe_string(item.get("FunctionName")),
                    "runtime": _safe_string(item.get("Runtime")),
                    "architecture": _safe_string(architecture),
                }
            )
        return resources, bool(response.get("NextMarker"))

    def _list_http_apis(self) -> tuple[list[JsonValue], bool]:
        client = self._client_factory("apigatewayv2", self._region)
        response = client.get_apis(MaxResults=str(self._limit))
        apis = response.get("Items", [])
        if not isinstance(apis, list):
            raise TypeError("Invalid API Gateway inventory response.")
        resources: list[JsonValue] = []
        for item in apis[: self._limit]:
            if not isinstance(item, dict):
                continue
            resources.append(
                {
                    "service": "api_gateway_v2",
                    "resource_type": "AWS::ApiGatewayV2::Api",
                    "name": _safe_string(item.get("Name")),
                    "protocol": _safe_string(item.get("ProtocolType")),
                    "default_endpoint_disabled": bool(
                        item.get("DisableExecuteApiEndpoint", False)
                    ),
                }
            )
        return resources, bool(response.get("NextToken"))


def _project_inventory_result(
    *,
    resources: list[JsonValue],
    sdk_requests: int,
    complete: bool,
    issues: list[AdapterIssue],
    region: str,
) -> AwsAdapterResult:
    status: Literal["ok", "partial", "error"]
    if complete and not issues:
        status = "ok"
    elif resources:
        status = "partial"
    else:
        status = "error"
    return AwsAdapterResult(
        data={
            "region": region,
            "read_only": True,
            "stacks": list(PROJECT_STACKS),
            "resources": resources,
            "total": len(resources),
            "complete": complete,
            "sdk_requests": sdk_requests,
            "writes": 0,
            "external_writes": 0,
        },
        sdk_requests=sdk_requests,
        resources=len(resources),
        status=status,
        issues=tuple(issues),
    )


_CFN_LOGICAL_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}\Z")
_CFN_RESOURCE_TYPE = re.compile(r"AWS::[A-Za-z0-9][A-Za-z0-9:.-]{1,127}\Z")
_CFN_STATUS = re.compile(r"[A-Z][A-Z0-9_]{1,63}\Z")
_ACCOUNT_ID = re.compile(r"\b\d{12}\b")


def _sanitize_physical_id(value: object) -> str:
    """Keep a useful identifier while dropping ARNs and account IDs."""

    if not isinstance(value, str) or not value:
        return "unknown"
    value = value[:MAX_NAME_CHARS]
    # Physical IDs are often ARNs. Returning only their final resource part
    # avoids exposing an ARN, region/account path, or account number.
    if value.startswith("arn:"):
        value = value.rsplit(":", 1)[-1]
    value = _ACCOUNT_ID.sub("<redacted-account>", value)
    value = _RESOURCE_ID_CHARS.sub("_", value)
    return value[:MAX_NAME_CHARS] or "unknown"


def _sanitize_cloudformation_resource(
    item: object, stack: str
) -> dict[str, JsonValue] | None:
    if not isinstance(item, Mapping):
        return None
    logical_id = item.get("LogicalResourceId")
    resource_type = item.get("ResourceType")
    status = item.get("ResourceStatus")
    if (
        not isinstance(logical_id, str)
        or _CFN_LOGICAL_ID.fullmatch(logical_id) is None
        or not isinstance(resource_type, str)
        or _CFN_RESOURCE_TYPE.fullmatch(resource_type) is None
        or not isinstance(status, str)
        or _CFN_STATUS.fullmatch(status) is None
    ):
        return None
    physical_id = item.get("PhysicalResourceId")
    if isinstance(physical_id, str) and any(
        ord(character) < 32 or ord(character) == 127 for character in physical_id
    ):
        return None
    return {
        "stack": stack,
        "logical_id": logical_id,
        "resource_type": resource_type,
        "physical_id": _sanitize_physical_id(physical_id),
        "status": status,
    }


def _validate_resource_explorer_query(query: str) -> str:
    if not query or len(query) > MAX_RESOURCE_EXPLORER_QUERY_CHARS:
        raise AdapterError(
            "invalid_resource_explorer_query",
            "Resource Explorer query must be non-empty and at most 256 characters.",
        )
    normalized = " ".join(query.split())
    if normalized == "*":
        return normalized
    if not normalized:
        raise AdapterError(
            "invalid_resource_explorer_query",
            "Resource Explorer query is invalid.",
        )

    seen_filters: set[str] = set()
    for token in normalized.split(" "):
        if token.lower() in {"not", "or"}:
            raise AdapterError(
                "invalid_resource_explorer_query",
                "Resource Explorer query contains unsupported syntax.",
            )
        if ":" not in token:
            if _RESOURCE_EXPLORER_KEYWORD.fullmatch(token) is None:
                raise AdapterError(
                    "invalid_resource_explorer_query",
                    "Resource Explorer query contains unsupported syntax.",
                )
            continue
        filter_name, value = token.split(":", 1)
        if filter_name in seen_filters or not value:
            raise AdapterError(
                "invalid_resource_explorer_query",
                "Resource Explorer query contains unsupported syntax.",
            )
        seen_filters.add(filter_name)
        if filter_name == "service":
            valid_filter = value in RESOURCE_EXPLORER_SERVICES
        elif filter_name == "region":
            valid_filter = (
                value == "global"
                or _RESOURCE_EXPLORER_REGION.fullmatch(value) is not None
            )
        elif filter_name == "resourcetype":
            match = _RESOURCE_EXPLORER_RESOURCE_TYPE.fullmatch(value)
            valid_filter = (
                match is not None and match.group(1) in RESOURCE_EXPLORER_SERVICES
            )
        else:
            valid_filter = False
        if not valid_filter:
            raise AdapterError(
                "invalid_resource_explorer_query",
                "Resource Explorer query contains an unsupported filter or value.",
            )
    return normalized


def _sanitize_resource_explorer_item(item: object) -> dict[str, JsonValue] | None:
    if not isinstance(item, Mapping):
        return None
    resource_arn = item.get("Arn")
    if not isinstance(resource_arn, str) or any(
        ord(character) < 32 or ord(character) == 127 for character in resource_arn
    ):
        return None
    arn_parts = resource_arn.split(":", 5)
    if (
        len(arn_parts) != 6
        or arn_parts[0] != "arn"
        or arn_parts[1] != "aws"
        or _RESOURCE_EXPLORER_SERVICE.fullmatch(arn_parts[2]) is None
        or (arn_parts[3] and _RESOURCE_EXPLORER_REGION.fullmatch(arn_parts[3]) is None)
        or (arn_parts[4] and re.fullmatch(r"\d{12}", arn_parts[4]) is None)
        or not arn_parts[5]
    ):
        return None

    service = item.get("Service")
    resource_type = item.get("ResourceType")
    region = item.get("Region")
    resource_type_match = (
        _RESOURCE_EXPLORER_RESOURCE_TYPE.fullmatch(resource_type)
        if isinstance(resource_type, str)
        else None
    )
    if (
        not isinstance(service, str)
        or _RESOURCE_EXPLORER_SERVICE.fullmatch(service) is None
        or not isinstance(resource_type, str)
        or resource_type_match is None
        or len(resource_type) > MAX_NAME_CHARS
        or resource_type_match.group(1) != service
        or not isinstance(region, str)
        or len(region) > 32
        or (region != "global" and _RESOURCE_EXPLORER_REGION.fullmatch(region) is None)
    ):
        return None
    resource_id = _RESOURCE_ID_CHARS.sub("_", arn_parts[5])[:MAX_NAME_CHARS]
    if not resource_id:
        return None
    return {
        "service": service,
        "resource_type": resource_type,
        "region": region,
        "resource_id": resource_id,
    }


def _resource_explorer_failure(
    *,
    query: str,
    result_limit: int,
    region: str,
    code: str,
    message: str,
    sdk_requests: int,
) -> AwsAdapterResult:
    return AwsAdapterResult(
        data={
            "region": region,
            "query": query,
            "max_results": result_limit,
            "read_only": True,
            "returned": 0,
            "truncated": False,
            "resources": [],
        },
        sdk_requests=sdk_requests,
        resources=0,
        status="error",
        issues=(AdapterIssue(code, message),),
    )
