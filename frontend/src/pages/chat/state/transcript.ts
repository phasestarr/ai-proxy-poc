import type { ChatHistoryMessage, ChatRequestMessage } from "../../../chat/api";

export type MessageRole = "user" | "assistant";
export type MessageStatus = "streaming" | "done" | "error";
export type MessageRequestMeta = {
  modelLabel: string;
  toolLabels: string[];
};

export type TranscriptMessage = {
  id: number;
  role: MessageRole;
  content: string;
  requestMeta?: MessageRequestMeta;
  status?: MessageStatus;
  streamStatusCode?: string;
  streamStatusMessage?: string;
  completionNote?: string;
  detail?: string;
  resultCode?: string | null;
  excludedFromRequest?: boolean;
};

export type HistorySelection = {
  modelId: string | null;
  toolIds: string[];
};

export function createPendingUserMessage(
  id: number,
  content: string,
  requestMeta?: MessageRequestMeta,
): TranscriptMessage {
  return {
    id,
    role: "user",
    content,
    requestMeta,
  };
}

export function createStreamingAssistantMessage(id: number): TranscriptMessage {
  return {
    id,
    role: "assistant",
    content: "",
    status: "streaming",
    streamStatusMessage: "Generating response...",
  };
}

export function buildRequestMessages(
  messages: TranscriptMessage[],
  nextUserMessage: TranscriptMessage,
): ChatRequestMessage[] {
  const transcriptMessages = messages
    .filter((message) => message.content.trim().length > 0)
    .filter((message) => !message.excludedFromRequest)
    .filter((message) => message.role === "user" || message.status !== "error")
    .map((message) => ({
      role: message.role,
      content: message.content,
    }));

  return [
    ...transcriptMessages,
    {
      role: nextUserMessage.role,
      content: nextUserMessage.content,
    },
  ];
}

export function appendAssistantDelta(
  messages: TranscriptMessage[],
  assistantMessageId: number,
  deltaText: string,
): TranscriptMessage[] {
  return messages.map((message) =>
    message.id === assistantMessageId
      ? {
          ...message,
          content: `${message.content}${deltaText}`,
        }
      : message,
  );
}

export function updateAssistantStatus(
  messages: TranscriptMessage[],
  assistantMessageId: number,
  statusCode: string,
  statusMessage: string,
): TranscriptMessage[] {
  return messages.map((message) =>
    message.id === assistantMessageId
      ? {
          ...message,
          streamStatusCode: statusCode,
          streamStatusMessage: statusMessage,
        }
      : message,
  );
}

export function completeAssistantMessage(
  messages: TranscriptMessage[],
  assistantMessageId: number,
  resultMessage: string,
  finishReason: string | null,
): TranscriptMessage[] {
  return messages.map((message) =>
    message.id === assistantMessageId
      ? {
          ...message,
          status: "done",
          streamStatusCode: undefined,
          streamStatusMessage: undefined,
          completionNote: resultMessage,
          resultCode: "success",
          detail: finishReason ? `finish reason: ${finishReason}` : undefined,
        }
      : message,
  );
}

export function failAssistantMessage(
  messages: TranscriptMessage[],
  userMessageId: number,
  assistantMessageId: number,
  resultCode: string | null,
  resultMessage: string,
  detail: string,
): TranscriptMessage[] {
  return messages.map((message) =>
    message.id === userMessageId
      ? {
          ...message,
          excludedFromRequest: true,
        }
      : message.id === assistantMessageId
      ? {
          ...message,
          streamStatusCode: undefined,
          streamStatusMessage: undefined,
          completionNote: resultMessage,
          detail,
          status: "error",
          resultCode,
          excludedFromRequest: true,
        }
      : message,
  );
}

export function mapHistoryMessagesToTranscript(
  historyMessages: ChatHistoryMessage[],
): { messages: TranscriptMessage[]; nextMessageId: number } {
  let nextMessageId = 1;
  const messages = [...historyMessages]
    .sort((left, right) => left.sequence - right.sequence)
    .map((message) => {
      const id = nextMessageId;
      nextMessageId += 1;

      return mapHistoryMessageToTranscriptMessage(message, id);
    });

  return { messages, nextMessageId };
}

export function getLatestHistorySelection(
  historyMessages: ChatHistoryMessage[],
): HistorySelection {
  const latestMessageWithSelection = [...historyMessages]
    .sort((left, right) => right.sequence - left.sequence)
    .find((message) => message.modelId || message.toolIds.length > 0);

  return {
    modelId: latestMessageWithSelection?.modelId ?? null,
    toolIds: latestMessageWithSelection?.toolIds ?? [],
  };
}

function mapHistoryMessageToTranscriptMessage(
  message: ChatHistoryMessage,
  id: number,
): TranscriptMessage {
  const status = message.status;
  const detail =
    message.resultMessage ??
    message.errorDetail ??
    (message.finishReason ? `finish reason: ${message.finishReason}` : undefined);

  return {
    id,
    role: message.role,
    content: message.content,
    requestMeta:
      message.role === "user" && (message.modelId || message.toolIds.length > 0)
        ? {
            modelLabel: message.modelId ?? "Saved model",
            toolLabels: message.toolIds,
          }
        : undefined,
    status: message.role === "assistant" ? status : undefined,
    completionNote: message.role === "assistant" && message.status === "done" ? message.resultMessage ?? undefined : undefined,
    detail: message.role === "assistant" && status === "error" ? detail : undefined,
    resultCode: message.resultCode,
    excludedFromRequest: message.excludedFromContext || message.status === "streaming",
  };
}
