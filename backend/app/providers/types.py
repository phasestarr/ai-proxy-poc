"""
Common provider contracts shared across provider implementations and service orchestration.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from enum import Enum
from typing import Literal


PriceEstimateCompleteness = Literal["complete", "partial"]
ProviderStreamEventKind = Literal[
    "answer_delta",
    "status",
    "completion",
    "heartbeat",
    "metadata",
]
ProviderBlockOperation = Literal["start", "delta", "end"]
ThinkingBlockOperation = ProviderBlockOperation
ToolBlockOperation = ProviderBlockOperation


@dataclass(slots=True, frozen=True)
class ProviderPriceEstimate:
    input_cost_usd: float = 0.0
    output_cost_usd: float = 0.0
    cache_read_cost_usd: float = 0.0
    cache_write_cost_usd: float = 0.0
    tool_cost_usd: float = 0.0
    total_cost_usd: float = 0.0
    currency: str = "USD"
    pricing_version: str | None = None
    completeness: PriceEstimateCompleteness = "complete"
    notes: tuple[str, ...] = ()


@dataclass(slots=True, frozen=True)
class ProviderUsageMetadata:
    prompt_token_count: int | None = None
    candidates_token_count: int | None = None
    total_token_count: int | None = None
    cache_read_input_tokens: int | None = None
    cache_write_input_tokens: int | None = None
    reasoning_token_count: int | None = None
    tool_result_prompt_token_count: int | None = None
    web_search_request_count: int | None = None
    file_search_request_count: int | None = None
    code_execution_request_count: int | None = None
    provider_raw_usage: dict[str, object] | None = None
    price_estimate: ProviderPriceEstimate | None = None


@dataclass(slots=True, frozen=True)
class ProviderRawStreamChunk:
    provider: str
    raw_chunk: object
    raw_event_type: str | None = None


@dataclass(slots=True, frozen=True)
class ThinkingDeltaBlock:
    block_id: str
    operation: ThinkingBlockOperation
    metadata: dict[str, object]
    text_delta: str = ""


@dataclass(slots=True, frozen=True)
class ToolUsageBlock:
    block_id: str
    operation: ToolBlockOperation
    metadata: dict[str, object]
    raw: object


ProviderBlock = ThinkingDeltaBlock | ToolUsageBlock


@dataclass(slots=True, frozen=True)
class ProviderStreamEvent:
    kind: ProviderStreamEventKind = "heartbeat"
    text_delta: str = ""
    append_to_message_content: bool = False
    stream_to_client: bool = True
    response_id: str | None = None
    model_version: str | None = None
    finish_reason: str | None = None
    usage: ProviderUsageMetadata | None = None
    block: ProviderBlock | None = None
    status_code: str | None = None
    status_message: str | None = None
    raw_event_type: str | None = None
    metadata: dict[str, object] | None = None


@dataclass(slots=True, frozen=True)
class ProviderToolDefinition:
    public_id: str
    display_name: str
    available: bool = True


@dataclass(slots=True, frozen=True)
class ProviderModelDefinition:
    public_id: str
    provider: str
    display_name: str
    available: bool = True
    supported_tools: tuple[ProviderToolDefinition, ...] = ()

    @property
    def supported_tool_ids(self) -> tuple[str, ...]:
        return tuple(tool.public_id for tool in self.supported_tools if tool.available)


@dataclass(slots=True, frozen=True)
class ProviderRoute:
    model: ProviderModelDefinition
    tool_ids: tuple[str, ...] = ()


@dataclass(slots=True, frozen=True)
class PreparedProviderChatRequest:
    provider: str
    public_model_id: str
    payload: object
    estimated_input_tokens: int
    input_token_count_payload: object | None = None
    resolved_input_tokens: int | None = None

    @property
    def budget_input_tokens(self) -> int:
        return self.resolved_input_tokens or self.estimated_input_tokens


def dump_provider_value(value: object) -> object:
    """Convert an SDK object to a JSON-compatible tree without selecting fields."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Enum):
        return dump_provider_value(value.value)
    if isinstance(value, dict):
        return {str(key): dump_provider_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [dump_provider_value(item) for item in value]

    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        try:
            dumped = model_dump(mode="json", by_alias=True, exclude_none=False)
        except TypeError:
            dumped = model_dump()
        return dump_provider_value(dumped)

    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return dump_provider_value(to_dict())
    if is_dataclass(value) and not isinstance(value, type):
        return dump_provider_value(asdict(value))
    if hasattr(value, "__dict__"):
        return dump_provider_value(
            {
                key: item
                for key, item in vars(value).items()
                if not key.startswith("_")
            }
        )
    return str(value)
