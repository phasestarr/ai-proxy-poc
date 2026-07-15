from __future__ import annotations

import unittest

from app.providers.anthropic.mapper import AnthropicStreamState, map_anthropic_stream_event
from app.providers.openai.mapper import OpenAIStreamState, map_openai_stream_event
from app.providers.types import ThinkingDeltaBlock, ToolUsageBlock
from app.providers.vertex.mapper import VertexStreamState, map_vertex_stream_chunk
from app.services.chat.completions.blocks import ProviderBlockAccumulator


class AnthropicStreamMappingTests(unittest.TestCase):
    def test_separates_thinking_raw_tools_and_answer_by_content_block_index(self) -> None:
        state = AnthropicStreamState()
        raw_events = [
            {
                "type": "message_start",
                "message": {"id": "msg_1", "model": "claude-sonnet-5"},
            },
            {
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "thinking", "thinking": "", "signature": ""},
            },
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "thinking_delta", "thinking": "Readable thought"},
            },
            {"type": "content_block_stop", "index": 0},
            {
                "type": "content_block_start",
                "index": 1,
                "content_block": {
                    "type": "server_tool_use",
                    "id": "srv_1",
                    "name": "web_search",
                    "input": {},
                },
            },
            {
                "type": "content_block_delta",
                "index": 1,
                "delta": {"type": "input_json_delta", "partial_json": "{\"query\":"},
            },
            {"type": "content_block_stop", "index": 1},
            {
                "type": "content_block_start",
                "index": 2,
                "content_block": {
                    "type": "web_search_tool_result",
                    "tool_use_id": "srv_1",
                    "content": [{"type": "web_search_result", "title": "Result", "url": "https://example.com"}],
                },
            },
            {"type": "content_block_stop", "index": 2},
            {
                "type": "content_block_start",
                "index": 3,
                "content_block": {"type": "text", "text": "Answer "},
            },
            {
                "type": "content_block_delta",
                "index": 3,
                "delta": {"type": "text_delta", "text": "body"},
            },
            {"type": "content_block_stop", "index": 3},
        ]

        mapped = [
            stream_event
            for raw_event in raw_events
            for stream_event in map_anthropic_stream_event(
                raw_event,
                state=state,
                public_model_id="claude-sonnet-4-6",
            )
        ]
        thinking = [event.block for event in mapped if isinstance(event.block, ThinkingDeltaBlock)]
        tools = [event.block for event in mapped if isinstance(event.block, ToolUsageBlock)]
        answer = "".join(event.text_delta for event in mapped if event.append_to_message_content)

        self.assertEqual([block.operation for block in thinking], ["start", "end"])
        self.assertEqual("".join(block.text_delta for block in thinking), "Readable thought")
        self.assertEqual(len(tools), 5)
        self.assertEqual([block.block_id for block in tools], ["anthropic:msg_1:tool:srv_1"] * 5)
        self.assertEqual([block.operation for block in tools], ["start", "delta", "delta", "delta", "end"])
        self.assertEqual(tools[0].raw, raw_events[4])
        self.assertEqual(tools[1].raw, raw_events[5])
        self.assertEqual(tools[-1].raw, raw_events[8])
        self.assertEqual(answer, "Answer body")


class OpenAIStreamMappingTests(unittest.TestCase):
    def test_correlates_summary_message_phase_and_generic_tool_lifecycle(self) -> None:
        state = OpenAIStreamState()
        raw_events = [
            {
                "type": "response.created",
                "sequence_number": 0,
                "response": {"id": "resp_1", "model": "gpt-5.5"},
            },
            {
                "type": "response.output_item.added",
                "sequence_number": 1,
                "output_index": 0,
                "item": {"type": "reasoning", "id": "rs_1", "encrypted_content": "opaque"},
            },
            {
                "type": "response.reasoning_summary_part.added",
                "sequence_number": 2,
                "output_index": 0,
                "item_id": "rs_1",
                "summary_index": 0,
                "part": {"type": "summary_text", "text": ""},
            },
            {
                "type": "response.reasoning_summary_text.delta",
                "sequence_number": 3,
                "output_index": 0,
                "item_id": "rs_1",
                "summary_index": 0,
                "delta": "**Search title**\n\nReadable summary",
                "obfuscation": "opaque",
            },
            {
                "type": "response.reasoning_summary_text.done",
                "sequence_number": 4,
                "output_index": 0,
                "item_id": "rs_1",
                "summary_index": 0,
                "text": "**Search title**\n\nReadable summary",
            },
            {
                "type": "response.output_item.added",
                "sequence_number": 5,
                "output_index": 1,
                "item": {"type": "web_search_call", "id": "ws_1", "status": "in_progress", "action": None},
            },
            {
                "type": "response.web_search_call.searching",
                "sequence_number": 6,
                "output_index": 1,
                "item_id": "ws_1",
            },
            {
                "type": "response.output_item.done",
                "sequence_number": 7,
                "output_index": 1,
                "item": {
                    "type": "web_search_call",
                    "id": "ws_1",
                    "status": "completed",
                    "action": {"type": "search", "query": "docs", "sources": []},
                },
            },
            {
                "type": "response.output_item.added",
                "sequence_number": 8,
                "output_index": 2,
                "item": {"type": "message", "id": "msg_1", "phase": "final_answer", "status": "in_progress"},
            },
            {
                "type": "response.output_text.delta",
                "sequence_number": 9,
                "output_index": 2,
                "item_id": "msg_1",
                "content_index": 0,
                "delta": "Final answer",
            },
            {
                "type": "response.output_text.done",
                "sequence_number": 10,
                "output_index": 2,
                "item_id": "msg_1",
                "content_index": 0,
                "text": "Final answer",
            },
            {
                "type": "response.completed",
                "sequence_number": 11,
                "response": {
                    "id": "resp_1",
                    "model": "gpt-5.5",
                    "status": "completed",
                    "output": [{"type": "message", "content": [{"type": "output_text", "text": "Final answer"}]}],
                    "usage": None,
                    "instructions": "must never become a block",
                },
            },
        ]

        mapped = [
            stream_event
            for raw_event in raw_events
            for stream_event in map_openai_stream_event(
                raw_event,
                state=state,
                public_model_id="gpt-5.4",
            )
        ]
        thinking = [event.block for event in mapped if isinstance(event.block, ThinkingDeltaBlock)]
        tools = [event.block for event in mapped if isinstance(event.block, ToolUsageBlock)]
        answer = "".join(event.text_delta for event in mapped if event.append_to_message_content)

        self.assertEqual([block.operation for block in thinking], ["start", "end"])
        self.assertEqual("".join(block.text_delta for block in thinking), "**Search title**\n\nReadable summary")
        self.assertEqual(thinking[0].metadata["response_id"], "resp_1")
        self.assertEqual(len(tools), 3)
        self.assertEqual([block.block_id for block in tools], ["openai:resp_1:tool:ws_1"] * 3)
        self.assertEqual([block.operation for block in tools], ["start", "delta", "end"])
        self.assertEqual(tools[1].raw, raw_events[6])
        self.assertEqual(tools[2].raw, raw_events[7])
        self.assertEqual(answer, "Final answer")
        self.assertFalse(any("instructions" in str(block.raw) for block in tools))

    def test_caller_managed_function_call_is_not_a_provider_native_tool_block(self) -> None:
        mapped = map_openai_stream_event(
            {
                "type": "response.output_item.added",
                "sequence_number": 1,
                "output_index": 0,
                "item": {"type": "function_call", "id": "fc_1", "name": "custom"},
            },
            state=OpenAIStreamState(),
            public_model_id="gpt-5.4",
        )
        self.assertEqual(mapped, ())


class VertexStreamMappingTests(unittest.TestCase):
    def test_mixed_chunk_emits_answer_thinking_and_one_unchanged_raw_tool_block(self) -> None:
        state = VertexStreamState()
        raw_chunk = {
            "sdkHttpResponse": {"headers": {"content-type": "application/json"}, "body": None},
            "responseId": "vertex_resp_1",
            "modelVersion": "gemini-3.5-flash",
            "usageMetadata": None,
            "candidates": [
                {
                    "content": {
                        "role": "model",
                        "parts": [
                            {"text": "**Locate docs**\n\nReadable thought", "thought": True},
                            {"text": "Final text", "thought": False, "thoughtSignature": "opaque"},
                        ],
                    },
                    "finishReason": "STOP",
                    "groundingMetadata": {
                        "webSearchQueries": ["official docs"],
                        "groundingChunks": [{"web": {"title": "Docs", "uri": "https://example.com"}}],
                        "groundingSupports": [],
                        "searchEntryPoint": {"renderedContent": "<div>provider widget</div>"},
                    },
                }
            ],
        }

        mapped = map_vertex_stream_chunk(
            raw_chunk,
            state=state,
            public_model_id="gemini-3-flash-preview",
        )
        thinking = [event.block for event in mapped if isinstance(event.block, ThinkingDeltaBlock)]
        tools = [event.block for event in mapped if isinstance(event.block, ToolUsageBlock)]
        answer = "".join(event.text_delta for event in mapped if event.append_to_message_content)

        self.assertEqual([block.operation for block in thinking], ["start", "end"])
        self.assertEqual(thinking[0].text_delta, "**Locate docs**\n\nReadable thought")
        self.assertEqual(thinking[0].metadata["value_path"], "$.candidates[0].content.parts[0].text")
        self.assertEqual(answer, "Final text")
        self.assertEqual(len(tools), 1)
        self.assertEqual(tools[0].block_id, "vertex_ai:vertex_resp_1:tool")
        self.assertEqual(tools[0].operation, "end")
        self.assertEqual(tools[0].raw, raw_chunk)
        self.assertEqual(tools[0].raw["sdkHttpResponse"]["headers"]["content-type"], "application/json")
        self.assertEqual(
            tools[0].raw["candidates"][0]["groundingMetadata"]["searchEntryPoint"]["renderedContent"],
            "<div>provider widget</div>",
        )
        self.assertEqual(mapped[-1].kind, "completion")

    def test_empty_thought_signature_is_not_a_thinking_block(self) -> None:
        state = VertexStreamState()
        mapped = map_vertex_stream_chunk(
            {
                "responseId": "vertex_resp_2",
                "candidates": [
                    {
                        "content": {"parts": [{"text": "", "thought": None, "thoughtSignature": "opaque"}]},
                        "finishReason": "STOP",
                    }
                ],
            },
            state=state,
            public_model_id="gemini-3-flash-preview",
        )
        self.assertFalse(any(isinstance(event.block, ThinkingDeltaBlock) for event in mapped))

    def test_caller_managed_function_call_does_not_create_a_tool_block(self) -> None:
        mapped = map_vertex_stream_chunk(
            {
                "responseId": "vertex_resp_3",
                "candidates": [
                    {
                        "content": {"parts": [{"text": "Answer", "thought": False, "functionCall": {"name": "custom"}}]},
                        "finishReason": "STOP",
                    }
                ],
            },
            state=VertexStreamState(),
            public_model_id="gemini-3-flash-preview",
        )
        self.assertFalse(any(isinstance(event.block, ToolUsageBlock) for event in mapped))

    def test_future_text_tool_payloads_share_one_response_tool_block(self) -> None:
        state = VertexStreamState()
        first = map_vertex_stream_chunk(
            {
                "responseId": "vertex_resp_4",
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {"futureTextToolPayload": {"query": "docs"}},
                            ],
                        },
                    }
                ],
            },
            state=state,
            public_model_id="gemini-3-flash-preview",
        )
        second = map_vertex_stream_chunk(
            {
                "responseId": "vertex_resp_4",
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {"futureTextToolResult": {"text": "result"}},
                            ],
                        },
                    }
                ],
            },
            state=state,
            public_model_id="gemini-3-flash-preview",
        )

        tools = [
            event.block
            for event in [*first, *second]
            if isinstance(event.block, ToolUsageBlock)
        ]

        self.assertEqual([block.block_id for block in tools], ["vertex_ai:vertex_resp_4:tool"] * 2)
        self.assertEqual([block.operation for block in tools], ["start", "delta"])


class ProviderBlockAccumulatorTests(unittest.TestCase):
    def test_accumulates_thinking_until_end(self) -> None:
        accumulator = ProviderBlockAccumulator()

        first = accumulator.ingest(
            ThinkingDeltaBlock(
                block_id="thinking-1",
                operation="start",
                text_delta="first ",
                metadata={"provider": "openai", "provider_event": "delta"},
            )
        )
        second = accumulator.ingest(
            ThinkingDeltaBlock(
                block_id="thinking-1",
                operation="delta",
                text_delta="second",
                metadata={"provider": "openai", "provider_event": "delta"},
            )
        )
        completed = accumulator.ingest(
            ThinkingDeltaBlock(
                block_id="thinking-1",
                operation="end",
                metadata={"provider": "openai", "provider_event": "done"},
            )
        )

        self.assertIsNone(first)
        self.assertIsNone(second)
        self.assertIsNotNone(completed)
        self.assertEqual(completed.type, "thinking")
        self.assertEqual(completed.provider_block_id, "thinking-1")
        self.assertEqual(completed.text, "first second")
        self.assertEqual(completed.metadata["provider_event"], "done")
        self.assertEqual(completed.raw_events, [])
        self.assertLessEqual(completed.started_at, completed.completed_at)

    def test_persists_end_only_tool_as_one_completed_block(self) -> None:
        accumulator = ProviderBlockAccumulator()
        raw = {"responseId": "vertex_resp_1", "groundingMetadata": {"queries": ["docs"]}}

        completed = accumulator.ingest(
            ToolUsageBlock(
                block_id="vertex_ai:vertex_resp_1:tool",
                operation="end",
                metadata={"provider": "vertex_ai", "provider_event": "generateContent.chunk"},
                raw=raw,
            )
        )

        self.assertIsNotNone(completed)
        self.assertEqual(completed.type, "tool")
        self.assertEqual(completed.provider_block_id, "vertex_ai:vertex_resp_1:tool")
        self.assertEqual(completed.raw_events, [raw])
        self.assertEqual(completed.text, "")


if __name__ == "__main__":
    unittest.main()
