"""Central fail-closed classification for downstream operations."""

from dataclasses import dataclass
from enum import StrEnum


class OperationClassification(StrEnum):
    FREE_VERIFIED_READ = "free_verified_read"
    CONTROLLED_BILLABLE = "controlled_billable"
    WRITE = "write"
    SENSITIVE_READ = "sensitive_read"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class OperationSpec:
    name: str
    classification: OperationClassification
    evidence: str


class OperationBlockedError(RuntimeError):
    def __init__(self, operation: str, classification: OperationClassification) -> None:
        self.operation = operation
        self.classification = classification
        super().__init__(
            f"Operation {operation!r} is blocked ({classification.value})."
        )


class OperationRegistry:
    """Allow automatic execution only for positively verified safe reads."""

    def __init__(self, specs: tuple[OperationSpec, ...] = ()) -> None:
        self._specs: dict[str, OperationSpec] = {}
        for spec in specs:
            self.register(spec)

    def register(self, spec: OperationSpec) -> None:
        if spec.name in self._specs:
            raise ValueError(f"Operation already registered: {spec.name}")
        self._specs[spec.name] = spec

    def classify(self, operation: str) -> OperationClassification:
        spec = self._specs.get(operation)
        return OperationClassification.UNKNOWN if spec is None else spec.classification

    def require_automatic(self, operation: str) -> OperationSpec:
        spec = self._specs.get(operation)
        classification = self.classify(operation)
        if (
            spec is None
            or classification is not OperationClassification.FREE_VERIFIED_READ
        ):
            raise OperationBlockedError(operation, classification)
        return spec


def build_default_registry() -> OperationRegistry:
    """Register only reviewed automatic operations; everything else fails closed."""

    return OperationRegistry(
        (
            OperationSpec(
                "aws.inventory.list",
                OperationClassification.FREE_VERIFIED_READ,
                "One non-paginated Lambda ListFunctions read and one API Gateway "
                "V2 GetApis read; AWS API and pricing references verified "
                "2026-09-02.",
            ),
            OperationSpec(
                "aws.cost_explorer.get_cost_and_usage",
                OperationClassification.CONTROLLED_BILLABLE,
                "Cost Explorer requests are potentially billable.",
            ),
            OperationSpec(
                "telegram.send_message",
                OperationClassification.WRITE,
                "External side effect requiring scoped confirmation.",
            ),
            OperationSpec(
                "trello.create_card",
                OperationClassification.WRITE,
                "External side effect requiring scoped confirmation.",
            ),
            OperationSpec(
                "secrets.read_value",
                OperationClassification.SENSITIVE_READ,
                "Credential-bearing reads are never exposed as general tools.",
            ),
        )
    )
