import { getApiErrorMessage, readJson } from "../../api/http";
import { AuthenticationRequiredError, readSessionConflict } from "../../auth/authErrors";
import type { ChatCompletionApiError, ChatHistoryApiEnvelope, ChatHistoryListApiEnvelope } from "./contracts";
import { mapHistoryMessage, mapHistorySummary } from "./mappers";
import type { ChatHistory, ChatHistorySummary } from "./types";

export async function fetchChatHistories(): Promise<ChatHistorySummary[]> {
  const response = await fetch("/api/v1/chat/histories", {
    credentials: "same-origin",
  });

  if (response.status === 401) {
    throw new AuthenticationRequiredError("login required");
  }

  if (response.status === 409) {
    throw await readSessionConflict(response);
  }

  const payload = (await readJson(response)) as ChatHistoryListApiEnvelope | ChatCompletionApiError | null;
  if (!response.ok) {
    throw new Error(getApiErrorMessage(response, payload, "failed to load chat histories"));
  }

  if (!payload || !("histories" in payload)) {
    throw new Error("invalid chat history payload");
  }

  return payload.histories.map(mapHistorySummary);
}

export async function fetchChatHistory(historyId: string): Promise<ChatHistory> {
  const response = await fetch(`/api/v1/chat/histories/${encodeURIComponent(historyId)}`, {
    credentials: "same-origin",
  });

  if (response.status === 401) {
    throw new AuthenticationRequiredError("login required");
  }

  if (response.status === 409) {
    throw await readSessionConflict(response);
  }

  const payload = (await readJson(response)) as ChatHistoryApiEnvelope | ChatCompletionApiError | null;
  if (!response.ok) {
    throw new Error(getApiErrorMessage(response, payload, "failed to load chat history"));
  }

  if (!payload || !("history" in payload) || !("messages" in payload)) {
    throw new Error("invalid chat history payload");
  }

  return {
    history: mapHistorySummary(payload.history),
    messages: payload.messages.map(mapHistoryMessage),
  };
}

export async function deleteChatHistory(historyId: string): Promise<void> {
  const response = await fetch(`/api/v1/chat/histories/${encodeURIComponent(historyId)}`, {
    method: "DELETE",
    credentials: "same-origin",
  });

  if (response.status === 401) {
    throw new AuthenticationRequiredError("login required");
  }

  if (response.status === 409) {
    throw await readSessionConflict(response);
  }

  if (!response.ok) {
    const payload = (await readJson(response)) as ChatCompletionApiError | null;
    throw new Error(getApiErrorMessage(response, payload, "failed to delete chat history"));
  }
}

export async function renameChatHistory(historyId: string, title: string): Promise<ChatHistorySummary> {
  const response = await fetch(`/api/v1/chat/histories/${encodeURIComponent(historyId)}/title`, {
    method: "PATCH",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ title }),
  });

  if (response.status === 401) {
    throw new AuthenticationRequiredError("login required");
  }

  if (response.status === 409) {
    throw await readSessionConflict(response);
  }

  const payload = (await readJson(response)) as ChatHistoryApiEnvelope["history"] | ChatCompletionApiError | null;
  if (!response.ok) {
    throw new Error(getApiErrorMessage(response, payload, "failed to rename chat history"));
  }

  if (!payload || !("id" in payload)) {
    throw new Error("invalid chat history payload");
  }

  return mapHistorySummary(payload);
}

export async function pinChatHistory(historyId: string): Promise<ChatHistorySummary> {
  return updatePinnedChatHistory(`/api/v1/chat/histories/${encodeURIComponent(historyId)}/pin`, "PUT");
}

export async function unpinChatHistory(historyId: string): Promise<ChatHistorySummary> {
  return updatePinnedChatHistory(`/api/v1/chat/histories/${encodeURIComponent(historyId)}/pin`, "DELETE");
}

async function updatePinnedChatHistory(url: string, method: "PUT" | "DELETE"): Promise<ChatHistorySummary> {
  const response = await fetch(url, {
    method,
    credentials: "same-origin",
  });

  if (response.status === 401) {
    throw new AuthenticationRequiredError("login required");
  }

  if (response.status === 409) {
    throw await readSessionConflict(response);
  }

  const payload = (await readJson(response)) as ChatHistoryApiEnvelope["history"] | ChatCompletionApiError | null;
  if (!response.ok) {
    throw new Error(getApiErrorMessage(response, payload, "failed to update chat pin state"));
  }

  if (!payload || !("id" in payload)) {
    throw new Error("invalid chat history payload");
  }

  return mapHistorySummary(payload);
}
