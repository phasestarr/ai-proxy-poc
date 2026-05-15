"""
Common provider contracts shared across provider implementations and service orchestration.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


PriceEstimateCompleteness = Literal["complete", "partial"]


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
class ProviderStreamChunk:
    text: str = ""
    response_id: str | None = None
    model_version: str | None = None
    finish_reason: str | None = None
    usage: ProviderUsageMetadata | None = None
    status_code: str | None = None
    status_message: str | None = None


@dataclass(slots=True, frozen=True)
class ProviderToolDefinition:
    public_id: str
    display_name: str
    available: bool = True


@dataclass(slots=True, frozen=True)
class ProviderFunctionDeclaration:
    name: str
    description: str
    parameters_json_schema: dict[str, object]


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
    function_declarations: tuple[ProviderFunctionDeclaration, ...] = ()


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
