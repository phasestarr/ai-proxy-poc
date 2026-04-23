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
          <div className={`chat-bubble ${message.role === "user" ? "chat-bubble--question" : "chat-bubble--answer"}`}>
            {message.role === "user" && message.requestMeta ? (
              <div className="chat-meta-row">
                <p className="chat-tag chat-tag--meta">{`Mode: ${message.requestMeta.modelLabel}`}</p>
                <p className="chat-tag chat-tag--meta">
                  {`Tools: ${message.requestMeta.toolLabels.length > 0 ? message.requestMeta.toolLabels.join(", ") : "None"}`}
                </p>
              </div>
            ) : null}
            {message.role === "assistant" && message.status === "streaming" && message.content.length === 0 ? (
              <p className="chat-loading">Generating response...</p>
            ) : message.role === "assistant" ? (
              <MarkdownMessage className="markdown-message" content={message.content} />
            ) : (
              <p className="chat-plain-text">{message.content}</p>
            )}
          </div>
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
