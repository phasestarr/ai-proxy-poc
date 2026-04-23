import { getApiErrorMessage, readJson } from "../../api/http";
import { AuthenticationRequiredError, SessionConflictError } from "../../auth/authErrors";
import { readSseStream } from "../../services/sse";
import type {
  ChatCompletionApiError,
  ChatStreamDeltaApiEvent,
  ChatStreamDoneApiEvent,
  ChatStreamErrorApiEvent,
  ChatStreamStartApiEvent,
} from "./contracts";
import { mapDoneEvent, mapStartEvent } from "./mappers";
import type { ChatStreamDone, StreamChatReplyOptions } from "./types";

export async function streamChatReply(options: StreamChatReplyOptions): Promise<ChatStreamDone> {
  const response = await fetch("/api/v1/chat/completions", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      Accept: "text/event-stream",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      chat_history_id: options.chatHistoryId ?? null,
      model_id: options.selection?.modelId ?? null,
      tool_ids: options.selection?.toolIds ?? [],
      messages: options.messages,
    }),
    signal: options.signal,
  });

  if (response.status === 401) {
    throw new AuthenticationRequiredError("login required");
  }

  if (response.status === 409) {
    const payload = (await readJson(response)) as ChatCompletionApiError | null;
    if (payload?.action === "session_conflict") {
      throw new SessionConflictError({
        reason: payload.reason ?? "session_conflict",
        detail: payload.detail ?? "This session needs attention.",
        redirectTo: payload.redirect_to ?? "/",
        canEvictOldest: payload.can_evict_oldest ?? false,
        authType: payload.auth_type ?? null,
        sessionLimit: payload.session_limit ?? null,
      });
    }

    throw new Error(getApiErrorMessage(response, payload, "request failed"));
  }

  if (!response.ok) {
    const payload = (await readJson(response)) as ChatCompletionApiError | null;
    throw new Error(getApiErrorMessage(response, payload, "request failed"));
  }

  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("text/event-stream")) {
    throw new Error("invalid streaming response");
  }

  if (!response.body) {
    throw new Error("streaming response body is unavailable");
  }

  let completion: ChatStreamDone | null = null;

  await readSseStream(response.body, (event) => {
    switch (event.event) {
      case "start": {
        options.onStart?.(mapStartEvent(JSON.parse(event.data) as ChatStreamStartApiEvent));
        return;
      }
      case "delta": {
        const payload = JSON.parse(event.data) as ChatStreamDeltaApiEvent;
        options.onDelta?.(payload.delta_text);
        return;
      }
      case "done": {
        completion = mapDoneEvent(JSON.parse(event.data) as ChatStreamDoneApiEvent);
        options.onDone?.(completion);
        return;
      }
      case "error": {
        const payload = JSON.parse(event.data) as ChatStreamErrorApiEvent;
        throw new Error(payload.result_message || payload.detail || "chat streaming failed");
      }
      default:
        return;
    }
  });

  if (!completion) {
    throw new Error("stream ended without a completion event");
  }

  return completion;
}
