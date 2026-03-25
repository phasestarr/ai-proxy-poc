import type { ChatRequestMessage } from "../services/chatService";

export type MessageRole = "user" | "assistant";
export type MessageStatus = "streaming" | "done" | "error";

export type TranscriptMessage = {
  id: number;
  role: MessageRole;
  content: string;
  status?: MessageStatus;
  completionNote?: string;
  detail?: string;
  excludedFromRequest?: boolean;
};

export function createPendingUserMessage(id: number, content: string): TranscriptMessage {
  return {
    id,
    role: "user",
    content,
  };
}

export function createStreamingAssistantMessage(id: number): TranscriptMessage {
  return {
    id,
    role: "assistant",
    content: "",
    status: "streaming",
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

export function completeAssistantMessage(
  messages: TranscriptMessage[],
  assistantMessageId: number,
  completionNote: string,
  finishReason: string | null,
): TranscriptMessage[] {
  return messages.map((message) =>
    message.id === assistantMessageId
      ? {
          ...message,
          status: "done",
          completionNote,
          detail: finishReason ? `finish reason: ${finishReason}` : undefined,
        }
      : message,
  );
}

export function excludeFailedExchange(
  messages: TranscriptMessage[],
  userMessageId: number,
  assistantMessageId: number,
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
            detail,
            content: message.content || "An error happened while processing your request.",
            status: "error",
            excludedFromRequest: true,
          }
        : message,
  );
}

export function removeExchange(
  messages: TranscriptMessage[],
  userMessageId: number,
  assistantMessageId: number,
): TranscriptMessage[] {
  return messages.filter((message) => message.id !== userMessageId && message.id !== assistantMessageId);
}
