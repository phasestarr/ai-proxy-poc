import type { ChatHistoryMessage, ChatStreamBlock } from "../../../chat/api";
import type { ChatModelOption } from "../../../chat/api/modelApi";

export type MessageRole = "user" | "assistant";
export type MessageStatus = "streaming" | "done" | "error";
export type MessageRequestMeta = {
  modelLabel: string;
  toolLabels: string[];
};
export type AssistantRenderOptions = {
  markdown: boolean;
  latex: boolean;
};

export type TranscriptMessage = {
  id: number;
  role: MessageRole;
  content: string;
  requestMeta?: MessageRequestMeta;
  status?: MessageStatus;
  streamStatusCode?: string;
  streamStatusMessage?: string;
  completionNote?: string;
  detail?: string;
  resultCode?: string | null;
  blocks?: ChatStreamBlock[];
  blocksCollapsed?: boolean;
  blocksAutoCollapsedForAnswer?: boolean;
  blockActivityStartedAtMs?: number;
  blockActivityCompletedAtMs?: number;
  blockActivityDurationMs?: number | null;
  excludedFromRequest?: boolean;
  renderOptions?: AssistantRenderOptions;
};

export type HistorySelection = {
  modelId: string | null;
  toolIds: string[];
};

export function createPendingUserMessage(
  id: number,
  content: string,
  requestMeta?: MessageRequestMeta,
): TranscriptMessage {
  return {
    id,
    role: "user",
    content,
    requestMeta,
  };
}

export function createStreamingAssistantMessage(id: number): TranscriptMessage {
  return {
    id,
    role: "assistant",
    content: "",
    status: "streaming",
    streamStatusMessage: "Generating response...",
    blocksCollapsed: false,
    renderOptions: createDefaultAssistantRenderOptions(),
  };
}

export function appendAssistantDelta(
  messages: TranscriptMessage[],
  assistantMessageId: number,
  deltaText: string,
): TranscriptMessage[] {
  return messages.map((message) =>
    message.id === assistantMessageId
      ? {
          ...message,
          content: `${message.content}${deltaText}`,
          blocksCollapsed:
            !message.blocksAutoCollapsedForAnswer && message.content.length === 0 && message.blocks && message.blocks.length > 0
              ? true
              : message.blocksCollapsed,
          blocksAutoCollapsedForAnswer:
            message.blocksAutoCollapsedForAnswer || message.content.length === 0,
        }
      : message,
  );
}

export function appendAssistantStreamBlock(
  messages: TranscriptMessage[],
  assistantMessageId: number,
  streamBlock: ChatStreamBlock,
): TranscriptMessage[] {
  const eventTimeMs = Date.now();
  return messages.map((message) => {
    if (message.id !== assistantMessageId) {
      return message;
    }

    const blocks = [...(message.blocks ?? [])];
    const matchingBlockIndex = blocks.findIndex((currentBlock) =>
      canMergeStreamBlocks(currentBlock, streamBlock),
    );
    if (matchingBlockIndex >= 0) {
      blocks[matchingBlockIndex] = mergeStreamBlocks(blocks[matchingBlockIndex], streamBlock);
    } else {
      blocks.push(streamBlock);
    }

    const blockActivityStartedAtMs = message.blockActivityStartedAtMs ?? eventTimeMs;
    return {
      ...message,
      blocks,
      blocksCollapsed: message.blocksCollapsed,
      blockActivityStartedAtMs,
      blockActivityCompletedAtMs: eventTimeMs,
      blockActivityDurationMs: eventTimeMs - blockActivityStartedAtMs,
    };
  });
}

export function updateAssistantStatus(
  messages: TranscriptMessage[],
  assistantMessageId: number,
  statusCode: string,
  statusMessage: string,
): TranscriptMessage[] {
  return messages.map((message) =>
    message.id === assistantMessageId
      ? {
          ...message,
          streamStatusCode: statusCode,
          streamStatusMessage: statusMessage,
        }
      : message,
  );
}

function canMergeStreamBlocks(previousBlock: ChatStreamBlock, nextBlock: ChatStreamBlock): boolean {
  return previousBlock.type === nextBlock.type && previousBlock.blockId === nextBlock.blockId;
}

function mergeStreamBlocks(previousBlock: ChatStreamBlock, nextBlock: ChatStreamBlock): ChatStreamBlock {
  if (previousBlock.type === "thinking" && nextBlock.type === "thinking") {
    return {
      ...previousBlock,
      operation: nextBlock.operation,
      text: `${previousBlock.text}${nextBlock.text}`,
      metadata: nextBlock.text ? nextBlock.metadata : previousBlock.metadata,
    };
  }

  if (previousBlock.type === "tool" && nextBlock.type === "tool") {
    return {
      ...previousBlock,
      operation: nextBlock.operation,
      metadata: nextBlock.metadata,
      rawEvents: [...previousBlock.rawEvents, ...nextBlock.rawEvents],
    };
  }

  return nextBlock;
}

export function completeAssistantMessage(
  messages: TranscriptMessage[],
  assistantMessageId: number,
  resultCode: string,
  resultMessage: string,
  finishReason: string | null,
): TranscriptMessage[] {
  return messages.map((message) =>
    message.id === assistantMessageId
      ? {
          ...message,
          status: "done",
          streamStatusCode: undefined,
          streamStatusMessage: undefined,
          completionNote: resultMessage,
          resultCode,
          detail: finishReason ? `finish reason: ${finishReason}` : undefined,
          blocksCollapsed: message.blocks && message.blocks.length > 0 ? true : message.blocksCollapsed,
        }
      : message,
  );
}

export function failAssistantMessage(
  messages: TranscriptMessage[],
  userMessageId: number,
  assistantMessageId: number,
  resultCode: string | null,
  resultMessage: string,
  detail: string,
): TranscriptMessage[] {
  return messages.map((message) =>
    message.id === userMessageId
      ? {
          ...message,
          excludedFromRequest: true,
        }
      : message.id === assistantMessageId
      ? {
          ...message,
          streamStatusCode: undefined,
          streamStatusMessage: undefined,
          completionNote: resultMessage,
          detail,
          status: "error",
          resultCode,
          blocksCollapsed: message.blocks && message.blocks.length > 0 ? true : message.blocksCollapsed,
          excludedFromRequest: true,
        }
      : message,
  );
}

export function mapHistoryMessagesToTranscript(
  historyMessages: ChatHistoryMessage[],
  modelOptions: ChatModelOption[] = [],
): { messages: TranscriptMessage[]; nextMessageId: number } {
  let nextMessageId = 1;
  const messages = [...historyMessages]
    .sort((left, right) => left.sequence - right.sequence)
    .map((message) => {
      const id = nextMessageId;
      nextMessageId += 1;

      return mapHistoryMessageToTranscriptMessage(message, id, modelOptions);
    });

  return { messages, nextMessageId };
}

export function getLatestHistorySelection(
  historyMessages: ChatHistoryMessage[],
): HistorySelection {
  const latestMessageWithSelection = [...historyMessages]
    .sort((left, right) => right.sequence - left.sequence)
    .find((message) => message.modelId || message.toolIds.length > 0);

  return {
    modelId: latestMessageWithSelection?.modelId ?? null,
    toolIds: latestMessageWithSelection?.toolIds ?? [],
  };
}

function mapHistoryMessageToTranscriptMessage(
  message: ChatHistoryMessage,
  id: number,
  modelOptions: ChatModelOption[],
): TranscriptMessage {
  const status = message.status;
  const detail =
    message.resultMessage ??
    message.errorDetail ??
    (message.finishReason ? `finish reason: ${message.finishReason}` : undefined);
  const requestMeta = message.role === "user" && (message.modelId || message.toolIds.length > 0)
    ? getRequestMeta(message.modelId, message.toolIds, modelOptions)
    : undefined;
  const blocks = [...message.blocks]
    .sort((left, right) => left.sequence - right.sequence)
    .map((block): ChatStreamBlock => {
      if (block.type === "thinking") {
        return {
          type: "thinking",
          operation: "end",
          blockId: block.blockId,
          text: block.text,
          metadata: block.metadata,
        };
      }

      return {
        type: "tool",
        operation: "end",
        blockId: block.blockId,
        metadata: block.metadata,
        rawEvents: block.rawEvents,
      };
    });

  return {
    id,
    role: message.role,
    content: message.content,
    requestMeta,
    status: message.role === "assistant" ? status : undefined,
    completionNote: message.role === "assistant" && message.status === "done" ? message.resultMessage ?? undefined : undefined,
    detail: message.role === "assistant" && status === "error" ? detail : undefined,
    resultCode: message.resultCode,
    blocks: message.role === "assistant" ? blocks : undefined,
    blocksCollapsed: message.role === "assistant" && blocks.length > 0 ? true : undefined,
    blocksAutoCollapsedForAnswer: message.role === "assistant" && blocks.length > 0 ? true : undefined,
    blockActivityStartedAtMs: message.blockActivityStartedAt ? Date.parse(message.blockActivityStartedAt) : undefined,
    blockActivityCompletedAtMs: message.blockActivityCompletedAt ? Date.parse(message.blockActivityCompletedAt) : undefined,
    blockActivityDurationMs: message.blockActivityDurationMs,
    excludedFromRequest: message.excludedFromContext || message.status === "streaming",
    renderOptions: message.role === "assistant" ? createDefaultAssistantRenderOptions() : undefined,
  };
}

export function toggleAssistantBlocks(
  messages: TranscriptMessage[],
  assistantMessageId: number,
): TranscriptMessage[] {
  return messages.map((message) => {
    if (message.id !== assistantMessageId || message.role !== "assistant" || !message.blocks || message.blocks.length === 0) {
      return message;
    }

    return {
      ...message,
      blocksCollapsed: !message.blocksCollapsed,
    };
  });
}

export function toggleAssistantMarkdown(
  messages: TranscriptMessage[],
  assistantMessageId: number,
): TranscriptMessage[] {
  return messages.map((message) => {
    if (message.id !== assistantMessageId || message.role !== "assistant") {
      return message;
    }

    const current = message.renderOptions ?? createDefaultAssistantRenderOptions();
    const markdown = !current.markdown;

    return {
      ...message,
      renderOptions: {
        markdown,
        latex: markdown,
      },
    };
  });
}

export function toggleAssistantLatex(
  messages: TranscriptMessage[],
  assistantMessageId: number,
): TranscriptMessage[] {
  return messages.map((message) => {
    if (message.id !== assistantMessageId || message.role !== "assistant") {
      return message;
    }

    const current = message.renderOptions ?? createDefaultAssistantRenderOptions();
    if (!current.markdown) {
      return message;
    }

    return {
      ...message,
      renderOptions: {
        ...current,
        latex: !current.latex,
      },
    };
  });
}

export function createDefaultAssistantRenderOptions(): AssistantRenderOptions {
  return {
    markdown: true,
    latex: true,
  };
}

function getRequestMeta(
  modelId: string | null,
  toolIds: string[],
  modelOptions: ChatModelOption[],
): MessageRequestMeta {
  const matchedModel = modelId ? modelOptions.find((option) => option.id === modelId) : undefined;
  const toolLabels = toolIds.map((toolId) => matchedModel?.toolOptions.find((tool) => tool.id === toolId)?.label ?? toolId);

  return {
    modelLabel: matchedModel?.label ?? modelId ?? "Saved model",
    toolLabels,
  };
}
