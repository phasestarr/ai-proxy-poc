import type {
  ChatHistoryMessageApiPayload,
  ChatHistorySummaryApiPayload,
  ChatStreamDoneApiEvent,
  ChatStreamStartApiEvent,
} from "./contracts";
import type { ChatHistoryMessage, ChatHistorySummary, ChatStreamDone, ChatStreamStart } from "./types";

export function mapStartEvent(payload: ChatStreamStartApiEvent): ChatStreamStart {
  return {
    model: payload.model,
    provider: payload.provider,
    chatHistoryId: payload.chat_history_id,
    userMessageId: payload.user_message_id,
    assistantMessageId: payload.assistant_message_id,
  };
}

export function mapDoneEvent(payload: ChatStreamDoneApiEvent): ChatStreamDone {
  return {
    model: payload.model,
    provider: payload.provider,
    finishReason: payload.finish_reason ?? null,
    usage: payload.usage
      ? {
          inputTokens: payload.usage.input_tokens ?? null,
          outputTokens: payload.usage.output_tokens ?? null,
          totalTokens: payload.usage.total_tokens ?? null,
        }
      : null,
  };
}

export function mapHistorySummary(payload: ChatHistorySummaryApiPayload): ChatHistorySummary {
  return {
    id: payload.id,
    title: payload.title,
    createdAt: payload.created_at,
    updatedAt: payload.updated_at,
    lastMessageAt: payload.last_message_at ?? null,
    messageCount: payload.message_count,
  };
}

export function mapHistoryMessage(payload: ChatHistoryMessageApiPayload): ChatHistoryMessage {
  return {
    id: payload.id,
    role: payload.role,
    content: payload.content,
    status: payload.status,
    sequence: payload.sequence,
    excludedFromContext: payload.excluded_from_context,
    modelId: payload.model_id ?? null,
    provider: payload.provider ?? null,
    toolIds: payload.tool_ids,
    finishReason: payload.finish_reason ?? null,
    errorDetail: payload.error_detail ?? null,
    createdAt: payload.created_at,
    updatedAt: payload.updated_at,
  };
}

