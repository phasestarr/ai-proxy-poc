import { FormEvent, startTransition, useLayoutEffect, useRef, useState } from "react";

import { getRandomCompletionNote, getRandomWelcomeText } from "../config/chatContent";
import MarkdownMessage from "../components/MarkdownMessage";
import { AuthenticationRequiredError, type AuthSession } from "../services/authService";
import { streamChatReply } from "../services/chatService";
import {
  appendAssistantDelta,
  buildRequestMessages,
  completeAssistantMessage,
  createPendingUserMessage,
  createStreamingAssistantMessage,
  excludeFailedExchange,
  removeExchange,
  type TranscriptMessage,
} from "./chat-page-state";
import "./chat-page.css";

const AUTO_SCROLL_THRESHOLD_PX = 96;
const TOOLS_ACTION_TAG = "[Tools]";

const actionButtons = ["Photo", "Model", "Tools"];

type ChatPageProps = {
  session: AuthSession;
  onLogout: () => Promise<void> | void;
  onSessionExpired: () => void;
};

export default function ChatPage({ session, onLogout, onSessionExpired }: ChatPageProps) {
  const [prompt, setPrompt] = useState("");
  const [messages, setMessages] = useState<TranscriptMessage[]>([]);
  const [isSending, setIsSending] = useState(false);
  const [welcomeText] = useState(() => getRandomWelcomeText());
  const conversationRef = useRef<HTMLDivElement | null>(null);
  const nextMessageIdRef = useRef(1);
  const shouldAutoScrollRef = useRef(true);

  const hasStarted = messages.length > 0;

  useLayoutEffect(() => {
    if (!conversationRef.current || !shouldAutoScrollRef.current) {
      return;
    }

    const frameId = window.requestAnimationFrame(() => {
      if (!conversationRef.current) {
        return;
      }

      conversationRef.current.scrollTop = conversationRef.current.scrollHeight;
    });

    return () => {
      window.cancelAnimationFrame(frameId);
    };
  }, [messages]);

  const handleConversationScroll = () => {
    if (!conversationRef.current) {
      return;
    }

    const { scrollHeight, scrollTop, clientHeight } = conversationRef.current;
    const distanceFromBottom = scrollHeight - scrollTop - clientHeight;
    shouldAutoScrollRef.current = distanceFromBottom <= AUTO_SCROLL_THRESHOLD_PX;
  };

  // dummy
  const appendActionTag = (tag: string) => {
    setPrompt((previous) => {
      const spacer = previous.trim().length > 0 ? " " : "";
      return `${previous}${spacer}[${tag}]`;
    });
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmedPrompt = prompt.trim();
    if (!trimmedPrompt || isSending) {
      return;
    }

    const { cleanPrompt, useRag } = parsePromptControlTags(trimmedPrompt);
    if (!cleanPrompt) {
      return;
    }

    const userMessageId = nextMessageIdRef.current;
    nextMessageIdRef.current += 1;

    const assistantMessageId = nextMessageIdRef.current;
    nextMessageIdRef.current += 1;

    const userMessage = createPendingUserMessage(userMessageId, cleanPrompt, useRag);
    const assistantMessage = createStreamingAssistantMessage(assistantMessageId);

    const requestMessages = buildRequestMessages(messages, userMessage);

    setPrompt("");
    setIsSending(true);
    shouldAutoScrollRef.current = true;
    setMessages((current) => [
      ...current,
      userMessage,
      assistantMessage,
    ]);

    try {
      await streamChatReply({
        messages: requestMessages,
        useRag,
        onDelta: (deltaText) => {
          startTransition(() => {
            setMessages((current) => appendAssistantDelta(current, assistantMessageId, deltaText));
          });
        },
        onDone: (completion) => {
          setMessages((current) =>
            completeAssistantMessage(current, assistantMessageId, getRandomCompletionNote(), completion.finishReason),
          );
        },
      });
    } catch (error) {
      if (error instanceof AuthenticationRequiredError) {
        setMessages((current) => removeExchange(current, userMessageId, assistantMessageId));
        onSessionExpired();
        return;
      }

      const detail = error instanceof Error ? error.message : "unknown error";
      setMessages((current) => excludeFailedExchange(current, userMessageId, assistantMessageId, detail));
    } finally {
      setIsSending(false);
    }
  };

  return (
    <main className={`chat-page ${hasStarted ? "chat-page--active" : ""}`}>
      <section className="chat-shell">
        {!hasStarted ? (
          <section className="welcome-panel">
            <p className="welcome-eyebrow">Welcome</p>
            <h1 className="welcome-title">{welcomeText}</h1>
          </section>
        ) : null}

        {hasStarted ? (
          <div className="conversation-list" onScroll={handleConversationScroll} ref={conversationRef}>
            {messages.map((message) => (
              <article className={`chat-message chat-message--${message.role}`} key={message.id}>
                <div className={`chat-bubble ${message.role === "user" ? "chat-bubble--question" : "chat-bubble--answer"}`}>
                  {message.role === "user" && message.grounded ? (
                    <p className="chat-tag chat-tag--grounded">[Grounded]</p>
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
        ) : null}

        <header className="chat-toolbar" role="group" aria-label="Session controls">
          <div className="chat-toolbar-copy">
            <p className="chat-toolbar-label">{session.authType === "guest" ? "Guest session" : "Microsoft session"}</p>
            <p className="chat-toolbar-name">{session.displayName}</p>
          </div>
          <button
            aria-label={`Log out ${session.displayName}`}
            className="chat-toolbar-button"
            onClick={() => void onLogout()}
            type="button"
          >
            Log Out
          </button>
        </header>

        <form className="composer" onSubmit={handleSubmit}>
          <textarea
            className="composer-input"
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
            placeholder="Type your prompt..."
            rows={3}
          />
          <div className="composer-actions">
            <div className="composer-action-group">
              {actionButtons.map((label) => (
                <button
                  className="composer-action-button"
                  key={label}
                  onClick={() => appendActionTag(label)}
                  type="button"
                >
                  {label}
                </button>
              ))}
            </div>
            <button className="composer-send-button" disabled={isSending || prompt.trim().length === 0} type="submit">
              {isSending ? "Streaming..." : "Send"}
            </button>
          </div>
        </form>
      </section>
    </main>
  );
}

function parsePromptControlTags(prompt: string): { cleanPrompt: string; useRag: boolean } {
  const useRag = prompt.includes(TOOLS_ACTION_TAG);
  const cleanPrompt = prompt.replaceAll(TOOLS_ACTION_TAG, " ").replace(/\s+/g, " ").trim();
  return { cleanPrompt, useRag };
}
