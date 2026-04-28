import type { RefObject } from "react";

import MarkdownMessage from "../../../components/MarkdownMessage";
import type { TranscriptMessage } from "../state/transcript";

type ConversationListProps = {
  messages: TranscriptMessage[];
  conversationRef: RefObject<HTMLDivElement>;
  onScroll: () => void;
};

export default function ConversationList({ messages, conversationRef, onScroll }: ConversationListProps) {
  return (
    <div className="conversation-list" onScroll={onScroll} ref={conversationRef}>
      {messages.map((message) => (
        <article className={`chat-message chat-message--${message.role}`} key={message.id}>
          <div className={`chat-content ${message.role === "user" ? "chat-content--question" : "chat-content--answer"}`}>
            {message.role === "assistant" && message.status === "streaming" && message.content.length === 0 ? (
              <p className="chat-loading">{message.streamStatusMessage ?? "Generating response..."}</p>
            ) : message.role === "assistant" ? (
              <MarkdownMessage className="markdown-message" content={message.content} />
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
          {message.role === "assistant" && message.status === "streaming" && message.content.length > 0 && message.streamStatusMessage ? (
            <p className="chat-loading">{message.streamStatusMessage}</p>
          ) : null}
          {message.role === "assistant" && message.status === "done" && message.completionNote ? (
            <p className="chat-done">{message.completionNote}</p>
          ) : null}
          {message.role === "assistant" && message.status === "error" && message.detail ? (
            <p className="chat-error">Error: {message.detail}</p>
          ) : null}
        </article>
      ))}
    </div>
  );
}
