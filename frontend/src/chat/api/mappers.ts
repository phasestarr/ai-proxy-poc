import type {
  ChatAttachmentLimitsApiPayload,
  ChatHistoryFileApiPayload,
  ChatHistoryMessageApiPayload,
  ChatHistorySummaryApiPayload,
  ChatStreamDoneApiEvent,
  ChatStreamBlockApiEvent,
  ChatStreamStartApiEvent,
  ChatStreamStatusApiEvent,
} from "./contracts";
import type {
  ChatAttachmentLimits,
  ChatHistoryFile,
  ChatHistoryMessage,
  ChatHistorySummary,
  ChatStreamBlock,
  ChatStreamDone,
  ChatStreamStart,
  ChatStreamStatus,
} from "./types";

export function mapStartEvent(payload: ChatStreamStartApiEvent): ChatStreamStart {
  return {
    model: payload.model ?? null,
    provider: payload.provider ?? null,
    chatHistoryId: payload.chat_history_id,
    userMessageId: payload.user_message_id,
    assistantMessageId: payload.assistant_message_id,
  };
}

export function mapDoneEvent(payload: ChatStreamDoneApiEvent): ChatStreamDone {
  return {
    model: payload.model ?? null,
    provider: payload.provider ?? null,
    resultCode: payload.result_code,
    resultMessage: payload.result_message,
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

export function mapStatusEvent(payload: ChatStreamStatusApiEvent): ChatStreamStatus {
  return {
    provider: payload.provider ?? null,
    statusCode: payload.status_code,
    statusMessage: payload.status_message,
  };
}

export function mapStreamBlock(payload: ChatStreamBlockApiEvent): ChatStreamBlock {
  if (payload.type === "thinking") {
    return {
      type: "thinking",
      operation: payload.operation,
      blockId: payload.block_id,
      text: payload.text_delta,
      metadata: payload.metadata,
    };
  }
  return {
    type: "tool",
    metadata: payload.metadata,
    raw: payload.raw,
  };
}

export function mapHistorySummary(payload: ChatHistorySummaryApiPayload): ChatHistorySummary {
  return {
    id: payload.id,
    title: payload.title,
    pinOrder: payload.pin_order ?? null,
    lifecycleState: payload.lifecycle_state ?? "active",
    operationState: payload.operation_state ?? "ready",
    operationType: payload.operation_type ?? null,
    createdAt: payload.created_at,
    updatedAt: payload.updated_at,
    lastMessageAt: payload.last_message_at ?? null,
    messageCount: payload.message_count,
    attachmentCount: payload.attachment_count,
  };
}

export function mapAttachmentLimits(payload: ChatAttachmentLimitsApiPayload): ChatAttachmentLimits {
  return {
    maxFilesPerHistory: payload.max_files_per_history,
    maxFilesPerUser: payload.max_files_per_user,
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
    resultCode: payload.result_code ?? null,
    resultMessage: payload.result_message ?? null,
    errorDetail: payload.error_detail ?? null,
    completedAt: payload.completed_at ?? null,
    createdAt: payload.created_at,
    updatedAt: payload.updated_at,
  };
}

export function mapHistoryFile(payload: ChatHistoryFileApiPayload): ChatHistoryFile {
  return {
    id: payload.id,
    displayName: payload.display_name,
    mimeType: payload.mime_type,
    byteSize: payload.byte_size,
    isActive: payload.is_active ?? true,
    tokenCounts: {
      openai: payload.token_counts?.openai ?? null,
      anthropic: payload.token_counts?.anthropic ?? null,
      vertexAi: payload.token_counts?.vertex_ai ?? null,
    },
    createdAt: payload.created_at,
    updatedAt: payload.updated_at,
  };
}
