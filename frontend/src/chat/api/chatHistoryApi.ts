import { getApiErrorMessage, readJson } from "../../api/http";
import { AuthenticationRequiredError, SessionConflictError } from "../../auth/authErrors";
import type {
  ChatCompletionApiError,
  ChatHistoryApiEnvelope,
  ChatHistoryFilesApiEnvelope,
  ChatHistoryListApiEnvelope,
} from "./contracts";
import { mapAttachmentLimits, mapHistoryFile, mapHistoryMessage, mapHistorySummary } from "./mappers";
import type { ChatHistory, ChatHistoryFilesMutation, ChatHistoryIndex, ChatHistorySummary } from "./types";

export async function fetchChatHistories(): Promise<ChatHistoryIndex> {
  const response = await fetch("/api/v1/chat/histories", {
    credentials: "same-origin",
  });

  if (response.status === 401) {
    throw new AuthenticationRequiredError("login required");
  }

  if (response.status === 409) {
    throw await readChatApiConflict(response, "failed to load chat histories");
  }

  const payload = (await readJson(response)) as ChatHistoryListApiEnvelope | ChatCompletionApiError | null;
  if (!response.ok) {
    throw new Error(getApiErrorMessage(response, payload, "failed to load chat histories"));
  }

  if (!payload || !("histories" in payload)) {
    throw new Error("invalid chat history payload");
  }

  return {
    histories: payload.histories.map(mapHistorySummary),
    attachmentLimits: mapAttachmentLimits(payload.attachment_limits),
  };
}

export async function fetchChatHistory(historyId: string): Promise<ChatHistory> {
  const response = await fetch(`/api/v1/chat/histories/${encodeURIComponent(historyId)}`, {
    credentials: "same-origin",
  });

  if (response.status === 401) {
    throw new AuthenticationRequiredError("login required");
  }

  if (response.status === 409) {
    throw await readChatApiConflict(response, "failed to load chat history");
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
    files: payload.files.map(mapHistoryFile),
    messages: payload.messages.map(mapHistoryMessage),
    attachmentLimits: mapAttachmentLimits(payload.attachment_limits),
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
    throw await readChatApiConflict(response, "failed to delete chat history");
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
    throw await readChatApiConflict(response, "failed to rename chat history");
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
    throw await readChatApiConflict(response, "failed to update chat pin state");
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

export async function uploadChatFile(
  file: File,
  chatHistoryId?: string | null,
): Promise<ChatHistoryFilesMutation> {
  const formData = new FormData();
  formData.append("file", file);
  if (chatHistoryId) {
    formData.append("chat_history_id", chatHistoryId);
  }

  const response = await fetch("/api/v1/chat/files", {
    method: "POST",
    credentials: "same-origin",
    body: formData,
  });

  if (response.status === 401) {
    throw new AuthenticationRequiredError("login required");
  }

  if (response.status === 409) {
    throw await readChatApiConflict(response, "failed to upload chat file");
  }

  const payload = (await readJson(response)) as ChatHistoryFilesApiEnvelope | ChatCompletionApiError | null;
  if (!response.ok) {
    throw new Error(getApiErrorMessage(response, payload, "failed to upload chat file"));
  }

  if (!payload || !("files" in payload) || !Array.isArray(payload.files)) {
    throw new Error("invalid chat file payload");
  }

  return {
    history: payload.history ? mapHistorySummary(payload.history) : null,
    files: payload.files.map(mapHistoryFile),
    deletedHistoryId: payload.deleted_history_id ?? null,
    attachmentLimits: mapAttachmentLimits(payload.attachment_limits),
  };
}

export async function deleteChatFile(historyId: string, fileId: string): Promise<ChatHistoryFilesMutation> {
  const response = await fetch(
    `/api/v1/chat/histories/${encodeURIComponent(historyId)}/files/${encodeURIComponent(fileId)}`,
    {
      method: "DELETE",
      credentials: "same-origin",
    },
  );

  if (response.status === 401) {
    throw new AuthenticationRequiredError("login required");
  }

  if (response.status === 409) {
    throw await readChatApiConflict(response, "failed to delete chat file");
  }

  const payload = (await readJson(response)) as ChatHistoryFilesApiEnvelope | ChatCompletionApiError | null;
  if (!response.ok) {
    throw new Error(getApiErrorMessage(response, payload, "failed to delete chat file"));
  }

  if (!payload || !("files" in payload) || !Array.isArray(payload.files)) {
    throw new Error("invalid chat file payload");
  }

  return {
    history: payload.history ? mapHistorySummary(payload.history) : null,
    files: payload.files.map(mapHistoryFile),
    deletedHistoryId: payload.deleted_history_id ?? null,
    attachmentLimits: mapAttachmentLimits(payload.attachment_limits),
  };
}

export async function updateChatFile(
  historyId: string,
  fileId: string,
  isActive: boolean,
): Promise<ChatHistoryFilesMutation> {
  const response = await fetch(
    `/api/v1/chat/histories/${encodeURIComponent(historyId)}/files/${encodeURIComponent(fileId)}`,
    {
      method: "PATCH",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ is_active: isActive }),
    },
  );

  if (response.status === 401) {
    throw new AuthenticationRequiredError("login required");
  }

  if (response.status === 409) {
    throw await readChatApiConflict(response, "failed to update chat file");
  }

  const payload = (await readJson(response)) as ChatHistoryFilesApiEnvelope | ChatCompletionApiError | null;
  if (!response.ok) {
    throw new Error(getApiErrorMessage(response, payload, "failed to update chat file"));
  }

  if (!payload || !("files" in payload) || !Array.isArray(payload.files)) {
    throw new Error("invalid chat file payload");
  }

  return {
    history: payload.history ? mapHistorySummary(payload.history) : null,
    files: payload.files.map(mapHistoryFile),
    deletedHistoryId: payload.deleted_history_id ?? null,
    attachmentLimits: mapAttachmentLimits(payload.attachment_limits),
  };
}


async function readChatApiConflict(response: Response, fallback: string): Promise<Error> {
  const payload = (await readJson(response)) as ChatCompletionApiError | null;
  if (payload?.action === "session_conflict") {
    return new SessionConflictError({
      reason: payload.reason ?? "session_conflict",
      detail: payload.detail ?? "This session needs attention.",
      redirectTo: payload.redirect_to ?? "/",
      canEvictOldest: payload.can_evict_oldest ?? false,
      authType: payload.auth_type ?? null,
      sessionLimit: payload.session_limit ?? null,
    });
  }
  return new Error(getApiErrorMessage(response, payload, fallback));
}
