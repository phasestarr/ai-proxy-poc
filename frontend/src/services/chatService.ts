import { AuthenticationRequiredError } from "./authService";
import { readSseStream } from "./sse";

const DEFAULT_MODEL = "vertex-default";

export type ChatRole = "system" | "user" | "assistant";

export type ChatRequestMessage = {
  role: ChatRole;
  content: string;
};

type ChatStreamStartApiEvent = {
  model: string;
  provider: string;
};

type ChatStreamDeltaApiEvent = {
  delta_text: string;
};

type ChatStreamDoneApiEvent = {
  model: string;
  provider: string;
  finish_reason: string | null;
  usage?: {
    input_tokens?: number | null;
    output_tokens?: number | null;
    total_tokens?: number | null;
  } | null;
};

type ChatStreamErrorApiEvent = {
  detail?: string;
};

type ChatCompletionApiError = {
  detail?: string;
};

export type ChatStreamStart = {
  model: string;
  provider: string;
};

export type ChatStreamDone = {
  model: string;
  provider: string;
  finishReason: string | null;
  usage: {
    inputTokens: number | null;
    outputTokens: number | null;
    totalTokens: number | null;
  } | null;
};

type StreamChatReplyOptions = {
  messages: ChatRequestMessage[];
  signal?: AbortSignal;
  onStart?: (event: ChatStreamStart) => void;
  onDelta?: (deltaText: string) => void;
  onDone?: (event: ChatStreamDone) => void;
};

export async function streamChatReply(options: StreamChatReplyOptions): Promise<ChatStreamDone> {
  const response = await fetch("/api/v1/chat/completions", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      Accept: "text/event-stream",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model: DEFAULT_MODEL,
      messages: options.messages,
    }),
    signal: options.signal,
  });

  if (response.status === 401) {
    throw new AuthenticationRequiredError("login required");
  }

  if (!response.ok) {
    const payload = (await readJson(response)) as ChatCompletionApiError | null;
    const detail = payload?.detail ? payload.detail : "request failed";
    throw new Error(`HTTP ${response.status}: ${detail}`);
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
        throw new Error(payload.detail || "chat streaming failed");
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

function mapStartEvent(payload: ChatStreamStartApiEvent): ChatStreamStart {
  return {
    model: payload.model,
    provider: payload.provider,
  };
}

function mapDoneEvent(payload: ChatStreamDoneApiEvent): ChatStreamDone {
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

async function readJson(response: Response): Promise<unknown | null> {
  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) {
    return null;
  }

  return response.json();
}
