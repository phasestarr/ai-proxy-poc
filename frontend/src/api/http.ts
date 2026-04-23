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
  return `HTTP ${response.status}: ${typeof detail === "string" && detail ? detail : fallback}`;
}

