export type ChatSelection = {
  modelId?: string | null;
  toolIds?: string[];
};

export type ChatOperationState = "ready" | "running" | "provider_streaming";

export type ChatAttachmentLimits = {
  maxFilesPerHistory: number;
  maxFilesPerUser: number;
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

export type ChatThinkingBlock = {
  type: "thinking";
  operation: "start" | "delta" | "end";
  blockId: string;
  text: string;
  metadata: Record<string, unknown>;
};

export type ChatToolUsageBlock = {
  type: "tool";
  operation: "start" | "delta" | "end";
  blockId: string;
  metadata: Record<string, unknown>;
  rawEvents: unknown[];
};

export type ChatStreamBlock = ChatThinkingBlock | ChatToolUsageBlock;

export type ChatHistoryMessageBlock = {
  id: string;
  type: "thinking" | "tool";
  sequence: number;
  blockId: string;
  text: string;
  metadata: Record<string, unknown>;
  rawEvents: unknown[];
  startedAt: string;
  completedAt: string;
  createdAt: string;
  updatedAt: string;
};

export type ChatHistorySummary = {
  id: string;
  title: string;
  pinOrder: number | null;
  lifecycleState: "active" | "deleting";
  operationState: ChatOperationState;
  operationType: string | null;
  createdAt: string;
  updatedAt: string;
  lastMessageAt: string | null;
  messageCount: number;
  attachmentCount: number;
};

export type ChatHistoryFile = {
  id: string;
  displayName: string;
  mimeType: string;
  byteSize: number;
  isActive: boolean;
  tokenCounts: {
    openai: number | null;
    anthropic: number | null;
    vertexAi: number | null;
  };
  createdAt: string;
  updatedAt: string;
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
  blocks: ChatHistoryMessageBlock[];
  blockActivityStartedAt: string | null;
  blockActivityCompletedAt: string | null;
  blockActivityDurationMs: number | null;
  completedAt: string | null;
  createdAt: string;
  updatedAt: string;
};

export type ChatHistory = {
  history: ChatHistorySummary;
  files: ChatHistoryFile[];
  messages: ChatHistoryMessage[];
  attachmentLimits: ChatAttachmentLimits;
};

export type ChatHistoryFilesMutation = {
  history: ChatHistorySummary | null;
  files: ChatHistoryFile[];
  deletedHistoryId: string | null;
  attachmentLimits: ChatAttachmentLimits;
};

export type ChatHistoryIndex = {
  histories: ChatHistorySummary[];
  attachmentLimits: ChatAttachmentLimits;
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
  prompt: string;
  selection?: ChatSelection;
  signal?: AbortSignal;
  onStart?: (event: ChatStreamStart) => void;
  onStatus?: (event: ChatStreamStatus) => void;
  onBlock?: (block: ChatStreamBlock) => void;
  onDelta?: (deltaText: string) => void;
  onDone?: (event: ChatStreamDone) => void;
  onError?: (event: {
    resultCode: string | null;
    resultMessage: string | null;
    detail: string | null;
    retryAfterSeconds: number | null;
  }) => void;
};
