type ModelToolApiPayload = {
  id: string;
  display_name: string;
  available: boolean;
};

type ModelApiPayload = {
  id: string;
  provider: string;
  display_name: string;
  available: boolean;
  default: boolean;
  tools: ModelToolApiPayload[];
};

type ModelListApiPayload = {
  data: ModelApiPayload[];
};

type ErrorPayload = {
  detail?: string;
};

export type ChatToolOption = {
  id: string;
  label: string;
  available: boolean;
};

export type ChatModelOption = {
  id: string;
  provider: string;
  label: string;
  available: boolean;
  default: boolean;
  toolOptions: ChatToolOption[];
};

export async function fetchAvailableModels(): Promise<ChatModelOption[]> {
  const response = await fetch("/api/v1/models", {
    credentials: "same-origin",
  });

  const payload = (await readJson(response)) as ModelListApiPayload | ErrorPayload | null;
  if (!response.ok) {
    const detail = payload && "detail" in payload && payload.detail ? payload.detail : "failed to load models";
    throw new Error(detail);
  }

  if (!payload || !("data" in payload) || !Array.isArray(payload.data)) {
    throw new Error("invalid model payload");
  }

  return payload.data.map(mapModel);
}

export function getChatModelOption(
  models: ChatModelOption[],
  modelId: string | null | undefined,
): ChatModelOption | undefined {
  return models.find((option) => option.id === modelId);
}

export function getDefaultChatModelId(models: ChatModelOption[]): string | null {
  const defaultModel = models.find((model) => model.default && model.available);
  if (defaultModel) {
    return defaultModel.id;
  }

  const firstAvailableModel = models.find((model) => model.available);
  return firstAvailableModel ? firstAvailableModel.id : null;
}

function mapModel(payload: ModelApiPayload): ChatModelOption {
  return {
    id: payload.id,
    provider: payload.provider,
    label: payload.display_name,
    available: payload.available,
    default: payload.default,
    toolOptions: payload.tools.map((tool) => ({
      id: tool.id,
      label: tool.display_name,
      available: tool.available,
    })),
  };
}

async function readJson(response: Response): Promise<unknown | null> {
  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) {
    return null;
  }

  return response.json();
}
