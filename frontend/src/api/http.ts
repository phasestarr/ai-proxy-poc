export type ErrorPayload = {
  detail?: string;
};

export async function readJson(response: Response): Promise<unknown | null> {
  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) {
    return null;
  }

  return response.json();
}

export function getApiErrorMessage(response: Response, payload: unknown, fallback: string): string {
  const detail = payload && typeof payload === "object" && "detail" in payload ? payload.detail : null;
  return `HTTP ${response.status}: ${formatApiErrorDetail(detail) ?? fallback}`;
}

function formatApiErrorDetail(detail: unknown): string | null {
  if (typeof detail === "string") {
    return detail.trim() || null;
  }

  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => formatValidationIssue(item))
      .filter((message): message is string => Boolean(message));
    return messages.length > 0 ? messages.join("; ") : null;
  }

  if (detail && typeof detail === "object") {
    return formatValidationIssue(detail) ?? JSON.stringify(detail);
  }

  return null;
}

function formatValidationIssue(issue: unknown): string | null {
  if (!issue || typeof issue !== "object") {
    return null;
  }

  const record = issue as Record<string, unknown>;
  const message = typeof record.msg === "string" ? record.msg : null;
  if (!message) {
    return null;
  }

  const location = Array.isArray(record.loc)
    ? record.loc
        .filter((part) => typeof part === "string" || typeof part === "number")
        .join(".")
    : "";

  return location ? `${location}: ${message}` : message;
}
