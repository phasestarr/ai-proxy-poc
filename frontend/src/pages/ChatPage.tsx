import { FormEvent, startTransition, useEffect, useRef, useState } from "react";

import { getRandomCompletionNote, getRandomWelcomeText } from "../config/chatContent";
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

  useEffect(() => {
    if (!conversationRef.current || !shouldAutoScrollRef.current) {
      return;
    }
    conversationRef.current.scrollTop = conversationRef.current.scrollHeight;
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

    const userMessageId = nextMessageIdRef.current;
    nextMessageIdRef.current += 1;

    const assistantMessageId = nextMessageIdRef.current;
    nextMessageIdRef.current += 1;

    const userMessage = createPendingUserMessage(userMessageId, trimmedPrompt);
    const assistantMessage = createStreamingAssistantMessage(assistantMessageId);

    const requestMessages = buildRequestMessages(messages, userMessage);

    setPrompt("");
    setIsSending(true);
    setMessages((current) => [
      ...current,
      userMessage,
      assistantMessage,
    ]);

    try {
      await streamChatReply({
        messages: requestMessages,
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
                  {message.role === "assistant" && message.status === "streaming" && message.content.length === 0 ? (
                    <p className="chat-loading">Generating response...</p>
                  ) : (
                    <p>{message.content}</p>
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
