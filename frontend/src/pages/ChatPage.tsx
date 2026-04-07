import { FormEvent, startTransition, useEffect, useLayoutEffect, useRef, useState } from "react";

import { getRandomCompletionNote, getRandomWelcomeText } from "../config/chatContent";
import MarkdownMessage from "../components/MarkdownMessage";
import { AuthenticationRequiredError, type AuthSession } from "../services/authService";
import { streamChatReply, type ChatSelection } from "../services/chatService";
import { fetchAvailableModels, getChatModelOption, getDefaultChatModelId, type ChatModelOption } from "../services/modelService";
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

type ChatPageProps = {
  session: AuthSession;
  onLogout: () => Promise<void> | void;
  onSessionExpired: () => void;
};

export default function ChatPage({ session, onLogout, onSessionExpired }: ChatPageProps) {
  const [prompt, setPrompt] = useState("");
  const [messages, setMessages] = useState<TranscriptMessage[]>([]);
  const [modelOptions, setModelOptions] = useState<ChatModelOption[]>([]);
  const [isModelsLoading, setIsModelsLoading] = useState(true);
  const [modelsError, setModelsError] = useState<string | null>(null);
  const [isSending, setIsSending] = useState(false);
  const [selectedModelId, setSelectedModelId] = useState<string | null>(null);
  const [selectedToolIds, setSelectedToolIds] = useState<string[]>([]);
  const [isModelMenuOpen, setIsModelMenuOpen] = useState(false);
  const [isToolsMenuOpen, setIsToolsMenuOpen] = useState(false);
  const [welcomeText] = useState(() => getRandomWelcomeText());
  const conversationRef = useRef<HTMLDivElement | null>(null);
  const modelMenuRef = useRef<HTMLDivElement | null>(null);
  const toolsMenuRef = useRef<HTMLDivElement | null>(null);
  const nextMessageIdRef = useRef(1);
  const shouldAutoScrollRef = useRef(true);

  const hasStarted = messages.length > 0;
  const selectedModel = getChatModelOption(modelOptions, selectedModelId);
  const availableTools = (selectedModel?.toolOptions ?? []).filter((tool) => tool.available);
  const selectedTools = availableTools.filter((tool) => selectedToolIds.includes(tool.id));
  const chatSelection: ChatSelection = {
    modelId: selectedModel?.id ?? null,
    toolIds: selectedToolIds,
  };
  const toolsButtonLabel =
    selectedTools.length > 0 ? `Tools: ${selectedTools.map((tool) => tool.label).join(", ")}` : "Tools: None";
  const isToolsButtonDisabled = !selectedModel?.available || availableTools.length === 0;
  const sessionLabel = getSessionLabel(session);

  useEffect(() => {
    let cancelled = false;

    const loadModels = async () => {
      try {
        const nextModels = await fetchAvailableModels();
        if (cancelled) {
          return;
        }

        setModelOptions(nextModels);
        setModelsError(null);
        setSelectedModelId((current) => {
          const currentModel = getChatModelOption(nextModels, current);
          return currentModel?.available ? current : getDefaultChatModelId(nextModels);
        });
      } catch (error) {
        if (cancelled) {
          return;
        }

        const detail = error instanceof Error ? error.message : "Failed to load model options.";
        setModelOptions([]);
        setModelsError(detail);
        setSelectedModelId(null);
      } finally {
        if (!cancelled) {
          setIsModelsLoading(false);
        }
      }
    };

    void loadModels();

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    setSelectedToolIds((current) =>
      current.filter((toolId) => selectedModel?.toolOptions.some((tool) => tool.available && tool.id === toolId)),
    );
  }, [selectedModel]);

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

  useEffect(() => {
    const handlePointerDown = (event: MouseEvent) => {
      const target = event.target;
      if (!(target instanceof Node)) {
        return;
      }

      if (modelMenuRef.current && !modelMenuRef.current.contains(target)) {
        setIsModelMenuOpen(false);
      }

      if (toolsMenuRef.current && !toolsMenuRef.current.contains(target)) {
        setIsToolsMenuOpen(false);
      }
    };

    document.addEventListener("mousedown", handlePointerDown);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
    };
  }, []);

  const handleModelSelect = (modelId: string) => {
    const nextModel = getChatModelOption(modelOptions, modelId);
    if (!nextModel?.available) {
      return;
    }

    setSelectedModelId(modelId);
    setSelectedToolIds([]);
    setIsModelMenuOpen(false);
    setIsToolsMenuOpen(false);
  };

  const handleToolToggle = (toolId: string) => {
    if (!availableTools.some((tool) => tool.id === toolId)) {
      return;
    }

    setSelectedToolIds((current) =>
      current.includes(toolId) ? current.filter((value) => value !== toolId) : [...current, toolId],
    );
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

    const userMessage = createPendingUserMessage(
      userMessageId,
      trimmedPrompt,
      {
        modelLabel: selectedModel?.label ?? "None",
        toolLabels: selectedTools.map((tool) => tool.label),
      },
    );
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
        selection: chatSelection,
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
        ) : null}

        <header className="chat-toolbar" role="group" aria-label="Session controls">
          <div className="chat-toolbar-copy">
            <p className="chat-toolbar-label">{session.authType === "guest" ? "Guest session" : "Microsoft session"}</p>
            <p className="chat-toolbar-name">{sessionLabel}</p>
          </div>
          <button
            aria-label={`Log out ${sessionLabel}`}
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
              <div className="composer-action-menu" ref={modelMenuRef}>
                <button
                  className="composer-action-button"
                  aria-expanded={isModelMenuOpen}
                  aria-haspopup="listbox"
                  disabled={isModelsLoading || modelOptions.length === 0}
                  onClick={() => {
                    setIsModelMenuOpen((current) => !current);
                    setIsToolsMenuOpen(false);
                  }}
                  type="button"
                >
                  <span>{`Model: ${selectedModel?.label ?? "None"}`}</span>
                  <span aria-hidden="true" className="composer-action-caret">
                    ▾
                  </span>
                </button>
                {isModelMenuOpen ? (
                  <div className="composer-popover" role="listbox">
                    {modelOptions.map((option) => (
                      <button
                        aria-selected={selectedModelId === option.id}
                        className={`composer-popover-option ${selectedModelId === option.id ? "composer-popover-option--selected" : ""}`}
                        disabled={!option.available}
                        key={option.id}
                        onClick={() => handleModelSelect(option.id)}
                        role="option"
                        type="button"
                      >
                        <span>{option.label}</span>
                        {!option.available ? <span className="composer-option-status">Coming soon</span> : null}
                      </button>
                    ))}
                  </div>
                ) : null}
              </div>

              <div className="composer-action-menu" ref={toolsMenuRef}>
                <button
                  className="composer-action-button"
                  aria-expanded={isToolsMenuOpen}
                  aria-haspopup="dialog"
                  disabled={isToolsButtonDisabled}
                  onClick={() => {
                    if (isToolsButtonDisabled) {
                      return;
                    }
                    setIsToolsMenuOpen((current) => !current);
                    setIsModelMenuOpen(false);
                  }}
                  type="button"
                >
                  <span>{toolsButtonLabel}</span>
                  <span aria-hidden="true" className="composer-action-caret">
                    ▾
                  </span>
                </button>
                {isToolsMenuOpen && !isToolsButtonDisabled ? (
                  <div className="composer-popover composer-popover--tools" role="dialog">
                    {availableTools.map((tool) => (
                      <label className="composer-tool-option" key={tool.id}>
                        <input
                          checked={selectedToolIds.includes(tool.id)}
                          onChange={() => handleToolToggle(tool.id)}
                          type="checkbox"
                        />
                        <span>{tool.label}</span>
                      </label>
                    ))}
                  </div>
                ) : null}
              </div>
            </div>
            <button
              className="composer-send-button"
              disabled={isSending || isModelsLoading || prompt.trim().length === 0 || !selectedModel?.available}
              type="submit"
            >
              {isSending ? "Streaming..." : "Send"}
            </button>
          </div>
          {modelsError ? <p className="chat-error">Error: {modelsError}</p> : null}
        </form>
      </section>
    </main>
  );
}

function getSessionLabel(session: AuthSession): string {
  if (session.authType === "microsoft" && session.email) {
    return maskEmail(session.email);
  }

  return session.displayName;
}

function maskEmail(email: string): string {
  const [localPart, domain] = email.split("@");
  if (!localPart || !domain) {
    return email;
  }

  const visiblePrefixLength = Math.min(2, localPart.length);
  const visiblePrefix = localPart.slice(0, visiblePrefixLength);
  return `${visiblePrefix}****@${domain}`;
}
