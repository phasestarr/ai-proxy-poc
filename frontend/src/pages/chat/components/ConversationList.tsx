import type { RefObject } from "react";

import MarkdownMessage from "../../../components/MarkdownMessage";
import type { TranscriptMessage } from "../state/transcript";

type ConversationListProps = {
  messages: TranscriptMessage[];
  conversationRef: RefObject<HTMLDivElement>;
  onScroll: () => void;
  onToggleMarkdown: (messageId: number) => void;
  onToggleLatex: (messageId: number) => void;
};

export default function ConversationList({
  messages,
  conversationRef,
  onScroll,
  onToggleMarkdown,
  onToggleLatex,
}: ConversationListProps) {
  return (
    <div className="conversation-list" onScroll={onScroll} ref={conversationRef}>
      {messages.map((message) => {
        const renderOptions = message.renderOptions ?? { markdown: true, latex: true };
        const markdownEnabled = renderOptions.markdown;
        const latexEnabled = renderOptions.markdown && renderOptions.latex;
        const isPlainTextAnswer = message.role === "assistant" && !markdownEnabled;
        const footerStatus = message.role === "assistant" ? buildAssistantFooterStatus(message) : null;

        return (
          <article className={`chat-message chat-message--${message.role}`} key={message.id}>
            <div
              className={`chat-content ${message.role === "user" ? "chat-content--question" : "chat-content--answer"} ${isPlainTextAnswer ? "chat-content--plain-answer" : ""}`}
            >
            {message.role === "assistant" && message.streamBlocks && message.streamBlocks.length > 0 ? (
              <div className="chat-provider-events">
                {message.streamBlocks.map((block, index) => {
                  if (block.type === "thinking") {
                    const presentation = parseThinkingText(block.text);
                    return (
                      <div className="chat-provider-event" key={`${message.id}-${block.blockId}-${index}`}>
                        <p className="chat-provider-event-label">{buildStreamBlockLabel(block)}</p>
                        {presentation.title ? (
                          <p className="chat-provider-event-title">{presentation.title}</p>
                        ) : null}
                        {presentation.body ? (
                          <MarkdownMessage
                            className="markdown-message chat-provider-event-text"
                            content={presentation.body}
                            enableLatex={latexEnabled}
                            enableMarkdown={markdownEnabled}
                          />
                        ) : null}
                      </div>
                    );
                  }
                  return (
                    <div className="chat-provider-event chat-provider-event--tool" key={`${message.id}-${block.blockId}-${index}`}>
                      <p className="chat-provider-event-label">{buildStreamBlockLabel(block)}</p>
                      <pre className="chat-provider-event-metadata">{JSON.stringify(block.rawEvents, null, 2)}</pre>
                    </div>
                  );
                })}
              </div>
            ) : null}
            {message.role === "assistant" && message.status === "streaming" && message.content.length === 0 && (!message.streamBlocks || message.streamBlocks.length === 0) ? (
              <p className={buildLoadingClassName(message.streamStatusCode)}>
                {message.streamStatusMessage ?? "Generating response..."}
              </p>
            ) : message.role === "assistant" ? (
              <MarkdownMessage
                className={`markdown-message ${isPlainTextAnswer ? "markdown-message--plain-frame" : ""}`}
                content={message.content}
                enableLatex={latexEnabled}
                enableMarkdown={markdownEnabled}
              />
            ) : (
              <div className="chat-user-bubble">
                <p className="chat-plain-text">{message.content}</p>
              </div>
            )}
            </div>
            {message.role === "user" && message.requestMeta ? (
              <div className="chat-request-meta">
                <p className="chat-request-meta-line">
                  {`Model: ${message.requestMeta.modelLabel} / Tools: ${
                    message.requestMeta.toolLabels.length > 0 ? message.requestMeta.toolLabels.join(", ") : "None"
                  }`}
                </p>
              </div>
            ) : null}
            {message.role === "assistant" ? (
              <div className="chat-footer">
                <div className="chat-footer-status">
                  {footerStatus ? <p className={footerStatus.className}>{footerStatus.text}</p> : null}
                </div>
                <div className="chat-render-controls" role="group" aria-label="Assistant response rendering controls">
                  <button
                    aria-label="Toggle Markdown rendering"
                    aria-pressed={markdownEnabled}
                    className={`chat-render-toggle ${markdownEnabled ? "chat-render-toggle--active" : ""}`}
                    onClick={() => onToggleMarkdown(message.id)}
                    title="Toggle Markdown rendering"
                    type="button"
                  >
                    <span aria-hidden="true">¶</span>
                  </button>
                  <button
                    aria-label="Toggle LaTeX rendering"
                    aria-pressed={latexEnabled}
                    className={`chat-render-toggle ${latexEnabled ? "chat-render-toggle--active" : ""}`}
                    disabled={!markdownEnabled}
                    onClick={() => onToggleLatex(message.id)}
                    title="Toggle LaTeX rendering"
                    type="button"
                  >
                    <span aria-hidden="true">∑</span>
                  </button>
                </div>
              </div>
            ) : null}
          </article>
        );
      })}
    </div>
  );
}

function buildStreamBlockLabel(block: NonNullable<TranscriptMessage["streamBlocks"]>[number]): string {
  const metadata = block.metadata;
  return [
    metadata.provider,
    metadata.semantic_type,
    metadata.provider_event,
    metadata.provider_subtype,
    metadata.value_path,
  ]
    .filter((value): value is string | number => typeof value === "string" || typeof value === "number")
    .join(" / ");
}

function parseThinkingText(text: string): { title: string | null; body: string } {
  const boldHeading = text.match(/^\*\*([^\r\n]+?)\*\*\r?\n(?:\r?\n)?/);
  if (boldHeading) {
    return {
      title: boldHeading[1],
      body: text.slice(boldHeading[0].length),
    };
  }

  const atxHeading = text.match(/^#{1,6}\s+([^\r\n]+)\r?\n(?:\r?\n)?/);
  if (atxHeading) {
    return {
      title: atxHeading[1],
      body: text.slice(atxHeading[0].length),
    };
  }

  return { title: null, body: text };
}

function buildAssistantFooterStatus(message: TranscriptMessage): { className: string; text: string } | null {
  if (message.status === "streaming" && message.content.length > 0 && message.streamStatusMessage) {
    return {
      className: buildLoadingClassName(message.streamStatusCode),
      text: message.streamStatusMessage,
    };
  }

  if (message.status === "done" && message.completionNote) {
    return {
      className: "chat-done",
      text: message.completionNote,
    };
  }

  if (message.status === "error" && message.detail) {
    return {
      className: "chat-error",
      text: `Error: ${message.detail}`,
    };
  }

  return null;
}

function buildLoadingClassName(statusCode?: string): string {
  if (statusCode?.startsWith("context_compaction")) {
    return "chat-loading chat-loading--compaction";
  }
  return "chat-loading";
}
