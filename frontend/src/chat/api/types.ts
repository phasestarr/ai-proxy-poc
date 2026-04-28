export type ChatRole = "system" | "user" | "assistant";

export type ChatRequestMessage = {
  role: ChatRole;
  content: string;
};

export type ChatSelection = {
  modelId?: string | null;
  toolIds?: string[];
};

export type ChatStreamStart = {
  model: string | null;
  provider: string | null;
  chatHistoryId: string;
  userMessageId: string;
  assistantMessageId: string;
};

export type ChatStreamStatus = {
  provider: string | null;
  statusCode: string;
  statusMessage: string;
};

export type ChatHistorySummary = {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  lastMessageAt: string | null;
  messageCount: number;
};

export type ChatHistoryMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  status: "done" | "streaming" | "error";
  sequence: number;
  excludedFromContext: boolean;
  modelId: string | null;
  provider: string | null;
  toolIds: string[];
  finishReason: string | null;
  resultCode: string | null;
  resultMessage: string | null;
  errorDetail: string | null;
  completedAt: string | null;
  createdAt: string;
  updatedAt: string;
};

export type ChatHistory = {
  history: ChatHistorySummary;
  messages: ChatHistoryMessage[];
};

export type ChatStreamDone = {
  model: string | null;
  provider: string | null;
  resultCode: string;
  resultMessage: string;
  finishReason: string | null;
  usage: {
    inputTokens: number | null;
    outputTokens: number | null;
    totalTokens: number | null;
  } | null;
};

export type StreamChatReplyOptions = {
  chatHistoryId?: string | null;
  messages: ChatRequestMessage[];
  selection?: ChatSelection;
  signal?: AbortSignal;
  onStart?: (event: ChatStreamStart) => void;
  onStatus?: (event: ChatStreamStatus) => void;
  onDelta?: (deltaText: string) => void;
  onDone?: (event: ChatStreamDone) => void;
  onError?: (event: {
    resultCode: string | null;
    resultMessage: string | null;
    detail: string | null;
    retryAfterSeconds: number | null;
  }) => void;
};
