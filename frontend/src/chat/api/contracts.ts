import type { AuthType } from "../../auth/authTypes";

export type ChatStreamStartApiEvent = {
  model?: string | null;
  provider?: string | null;
  chat_history_id: string;
  user_message_id: string;
  assistant_message_id: string;
};

export type ChatStreamDeltaApiEvent = {
  delta_text: string;
};

export type ChatStreamStatusApiEvent = {
  provider?: string | null;
  status_code: string;
  status_message: string;
};

export type ChatStreamDoneApiEvent = {
  model?: string | null;
  provider?: string | null;
  result_code: string;
  result_message: string;
  finish_reason: string | null;
  usage?: {
    input_tokens?: number | null;
    output_tokens?: number | null;
    total_tokens?: number | null;
  } | null;
};

export type ChatStreamErrorApiEvent = {
  result_code?: string;
  result_message?: string;
  retry_after_seconds?: number | null;
  detail?: string;
};

export type ChatCompletionApiError = {
  action?: "login" | "session_conflict";
  detail?: string;
  reason?: string;
  redirect_to?: string;
  can_evict_oldest?: boolean;
  auth_type?: AuthType | null;
  session_limit?: number | null;
};

export type ChatHistorySummaryApiPayload = {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  last_message_at?: string | null;
  message_count: number;
};

export type ChatHistoryMessageApiPayload = {
  id: string;
  role: "user" | "assistant";
  content: string;
  status: "done" | "streaming" | "error";
  sequence: number;
  excluded_from_context: boolean;
  model_id?: string | null;
  provider?: string | null;
  tool_ids: string[];
  finish_reason?: string | null;
  result_code?: string | null;
  result_message?: string | null;
  error_detail?: string | null;
  completed_at?: string | null;
  created_at: string;
  updated_at: string;
};

export type ChatHistoryListApiEnvelope = {
  histories: ChatHistorySummaryApiPayload[];
};

export type ChatHistoryApiEnvelope = {
  history: ChatHistorySummaryApiPayload;
  messages: ChatHistoryMessageApiPayload[];
};
