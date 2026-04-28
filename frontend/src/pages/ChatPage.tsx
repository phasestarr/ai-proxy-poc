import { FormEvent, startTransition, useEffect, useRef, useState } from "react";

import { getRandomWelcomeText } from "../config/chatContent";
import { AuthenticationRequiredError, SessionConflictError } from "../auth/authErrors";
import type { AuthSession, SessionConflictInfo } from "../auth/authTypes";
import {
  deleteChatHistory,
  fetchChatHistories,
  fetchChatHistory,
  pinChatHistory,
  renameChatHistory,
  streamChatReply,
  type ChatHistorySummary,
  unpinChatHistory,
} from "../chat/api";
import Composer, { buildChatSelection } from "./chat/components/Composer";
import ConversationList from "./chat/components/ConversationList";
import HistoryRail from "./chat/components/HistoryRail";
import { useChatModelSelection } from "./chat/hooks/useChatModelSelection";
import { useConversationAutoScroll } from "./chat/hooks/useConversationAutoScroll";
import {
  appendAssistantDelta,
  buildRequestMessages,
  completeAssistantMessage,
  createPendingUserMessage,
  createStreamingAssistantMessage,
  failAssistantMessage,
  getLatestHistorySelection,
  mapHistoryMessagesToTranscript,
  type TranscriptMessage,
  updateAssistantStatus,
} from "./chat/state/transcript";
import "./chat/styles/chat.css";

type ChatPageProps = {
  session: AuthSession;
  onLogout: () => Promise<void> | void;
  onSessionExpired: () => void;
  onSessionConflict: (conflict: SessionConflictInfo) => void;
};

const APP_NAME = "0.2.5-pre-Procyon";

export default function ChatPage({ session, onLogout, onSessionExpired, onSessionConflict }: ChatPageProps) {
  const [prompt, setPrompt] = useState("");
  const [messages, setMessages] = useState<TranscriptMessage[]>([]);
  const [isSending, setIsSending] = useState(false);
  const [activeChatHistoryId, setActiveChatHistoryId] = useState<string | null>(null);
  const [historySummaries, setHistorySummaries] = useState<ChatHistorySummary[]>([]);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [sendError, setSendError] = useState<string | null>(null);
  const [isHistoryLoading, setIsHistoryLoading] = useState(true);
  const [loadingHistoryId, setLoadingHistoryId] = useState<string | null>(null);
  const [deletingHistoryId, setDeletingHistoryId] = useState<string | null>(null);
  const [updatingHistoryId, setUpdatingHistoryId] = useState<string | null>(null);
  const [welcomeText, setWelcomeText] = useState(() => getRandomWelcomeText());
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const nextMessageIdRef = useRef(1);
  const models = useChatModelSelection();
  const autoScroll = useConversationAutoScroll(messages);

  const hasStarted = messages.length > 0;
  const chatSelection = buildChatSelection(models.selectedModel, models.selectedToolIds);

  const handleRecoverableError = (error: unknown, fallback: string) => {
    if (error instanceof AuthenticationRequiredError) {
      onSessionExpired();
      return true;
    }

    if (error instanceof SessionConflictError) {
      onSessionConflict(error.conflict);
      return true;
    }

    setHistoryError(error instanceof Error ? error.message : fallback);
    return false;
  };

  const refreshHistorySummaries = async () => {
    try {
      const histories = await fetchChatHistories();
      setHistorySummaries(histories);
      setHistoryError(null);
    } catch (error) {
      handleRecoverableError(error, "Failed to load chat histories.");
    } finally {
      setIsHistoryLoading(false);
    }
  };

  useEffect(() => {
    setIsHistoryLoading(true);
    setHistoryError(null);
    setHistorySummaries([]);
    setMessages([]);
    setPrompt("");
    setActiveChatHistoryId(null);
    setSendError(null);
    setWelcomeText(getRandomWelcomeText());
    nextMessageIdRef.current = 1;

    let cancelled = false;
    const loadHistories = async () => {
      try {
        const histories = await fetchChatHistories();
        if (cancelled) {
          return;
        }
        setHistorySummaries(histories);
        setHistoryError(null);
      } catch (error) {
        if (cancelled) {
          return;
        }
        handleRecoverableError(error, "Failed to load chat histories.");
      } finally {
        if (!cancelled) {
          setIsHistoryLoading(false);
        }
      }
    };

    void loadHistories();

    return () => {
      cancelled = true;
    };
  }, [session.userId]);

  const handleNewChat = () => {
    if (isSending) {
      return;
    }

    setActiveChatHistoryId(null);
    setMessages([]);
    setPrompt("");
    setSendError(null);
    setWelcomeText(getRandomWelcomeText());
    nextMessageIdRef.current = 1;
    models.resetModelSelection();
    autoScroll.enableAutoScroll();
  };

  const handleSelectHistory = async (historyId: string) => {
    if (isSending || loadingHistoryId || historyId === activeChatHistoryId) {
      return;
    }

    setLoadingHistoryId(historyId);
    setHistoryError(null);
    setSendError(null);
    try {
      const history = await fetchChatHistory(historyId);
      const mapped = mapHistoryMessagesToTranscript(history.messages, models.modelOptions);
      const latestSelection = getLatestHistorySelection(history.messages);
      setActiveChatHistoryId(history.history.id);
      setMessages(mapped.messages);
      models.setSelectedModelId(latestSelection.modelId);
      models.setSelectedToolIds(latestSelection.toolIds);
      nextMessageIdRef.current = mapped.nextMessageId;
      autoScroll.enableAutoScroll();
      setPrompt("");
    } catch (error) {
      handleRecoverableError(error, "Failed to load chat history.");
    } finally {
      setLoadingHistoryId(null);
    }
  };

  const handleDeleteHistory = async (historyId: string) => {
    if (isSending || deletingHistoryId || updatingHistoryId) {
      return;
    }

    setDeletingHistoryId(historyId);
    setHistoryError(null);
    setSendError(null);
    try {
      await deleteChatHistory(historyId);
      setHistorySummaries((current) => current.filter((history) => history.id !== historyId));
      if (activeChatHistoryId === historyId) {
        handleNewChat();
      }
    } catch (error) {
      handleRecoverableError(error, "Failed to delete chat history.");
    } finally {
      setDeletingHistoryId(null);
    }
  };

  const handleRenameHistory = async (historyId: string, title: string) => {
    if (isSending || deletingHistoryId || updatingHistoryId) {
      return;
    }

    setUpdatingHistoryId(historyId);
    setHistoryError(null);
    setSendError(null);
    try {
      await renameChatHistory(historyId, title);
      await refreshHistorySummaries();
    } catch (error) {
      handleRecoverableError(error, "Failed to rename chat history.");
    } finally {
      setUpdatingHistoryId(null);
    }
  };

  const handleTogglePinHistory = async (historyId: string, isPinned: boolean) => {
    if (isSending || deletingHistoryId || updatingHistoryId) {
      return;
    }

    setUpdatingHistoryId(historyId);
    setHistoryError(null);
    setSendError(null);
    try {
      if (isPinned) {
        await unpinChatHistory(historyId);
      } else {
        await pinChatHistory(historyId);
      }
      await refreshHistorySummaries();
    } catch (error) {
      handleRecoverableError(error, "Failed to update chat pin state.");
    } finally {
      setUpdatingHistoryId(null);
    }
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
        modelLabel: models.selectedModel?.label ?? "None",
        toolLabels: models.selectedTools.map((tool) => tool.label),
      },
    );
    const assistantMessage = createStreamingAssistantMessage(assistantMessageId);

    const requestMessages = buildRequestMessages(messages, userMessage);

    let didStart = false;
    let streamErrorHandled = false;

    setSendError(null);
    setIsSending(true);
    autoScroll.enableAutoScroll();

    try {
      await streamChatReply({
        chatHistoryId: activeChatHistoryId,
        messages: requestMessages,
        selection: chatSelection,
        onStart: (start) => {
          didStart = true;
          setActiveChatHistoryId(start.chatHistoryId);
          setPrompt("");
          setMessages((current) => [
            ...current,
            userMessage,
            assistantMessage,
          ]);
          void refreshHistorySummaries();
        },
        onStatus: (statusEvent) => {
          setMessages((current) =>
            updateAssistantStatus(current, assistantMessageId, statusEvent.statusCode, statusEvent.statusMessage),
          );
        },
        onDelta: (deltaText) => {
          startTransition(() => {
            setMessages((current) => appendAssistantDelta(current, assistantMessageId, deltaText));
          });
        },
        onDone: (completion) => {
          setMessages((current) =>
            completeAssistantMessage(current, assistantMessageId, completion.resultMessage, completion.finishReason),
          );
        },
        onError: (streamError) => {
          streamErrorHandled = true;
          const detail = streamError.detail ?? streamError.resultMessage ?? "chat streaming failed";
          const resultMessage = streamError.resultMessage ?? detail;
          setMessages((current) =>
            failAssistantMessage(
              current,
              userMessageId,
              assistantMessageId,
              streamError.resultCode,
              resultMessage,
              detail,
            ),
          );
        },
      });
    } catch (error) {
      if (error instanceof AuthenticationRequiredError) {
        onSessionExpired();
        return;
      }

      if (error instanceof SessionConflictError) {
        onSessionConflict(error.conflict);
        return;
      }

      const detail = error instanceof Error ? error.message : "unknown error";
      if (!didStart) {
        setSendError(detail);
      } else if (!streamErrorHandled) {
        setMessages((current) =>
          failAssistantMessage(current, userMessageId, assistantMessageId, null, detail, detail),
        );
      }
    } finally {
      setIsSending(false);
      if (didStart) {
        void refreshHistorySummaries();
      }
    }
  };

  return (
    <main
      className={`chat-page ${hasStarted ? "chat-page--active" : "chat-page--idle"} ${isSidebarOpen ? "chat-page--sidebar-open" : "chat-page--sidebar-closed"}`}
    >
      <HistoryRail
        appName={APP_NAME}
        activeHistoryId={activeChatHistoryId}
        deletingHistoryId={deletingHistoryId}
        histories={historySummaries}
        historyError={historyError}
        isHistoryLoading={isHistoryLoading}
        isOpen={isSidebarOpen}
        isSending={isSending}
        loadingHistoryId={loadingHistoryId}
        updatingHistoryId={updatingHistoryId}
        onSidebarToggle={() => {
          setIsSidebarOpen((current) => !current);
        }}
        onDeleteHistory={handleDeleteHistory}
        onNewChat={handleNewChat}
        onRenameHistory={handleRenameHistory}
        onSelectHistory={handleSelectHistory}
        onTogglePinHistory={handleTogglePinHistory}
        session={session}
      />
      <section className={`chat-shell ${hasStarted ? "chat-shell--conversation" : "chat-shell--idle"}`}>
        {!hasStarted ? (
          <section className="welcome-panel">
            <h1 className="welcome-title">{welcomeText}</h1>
          </section>
        ) : null}

        {hasStarted ? (
          <ConversationList
            conversationRef={autoScroll.conversationRef}
            messages={messages}
            onScroll={autoScroll.handleConversationScroll}
          />
        ) : null}

        <Composer
          availableTools={models.availableTools}
          isModelMenuOpen={models.isModelMenuOpen}
          isModelsLoading={models.isModelsLoading}
          isSending={isSending}
          isToolsMenuOpen={models.isToolsMenuOpen}
          modelMenuRef={models.modelMenuRef}
          modelOptions={models.modelOptions}
          modelsError={models.modelsError}
          onModelMenuToggle={models.handleModelMenuToggle}
          onModelSelect={models.handleModelSelect}
          onLogout={onLogout}
          onPromptChange={(value) => {
            setPrompt(value);
          }}
          onSubmit={handleSubmit}
          onToolToggle={models.handleToolToggle}
          onToolsMenuToggle={models.handleToolsMenuToggle}
          prompt={prompt}
          sendError={sendError}
          selectedModel={models.selectedModel}
          selectedModelId={models.selectedModelId}
          selectedToolIds={models.selectedToolIds}
          selectedTools={models.selectedTools}
          toolsMenuRef={models.toolsMenuRef}
        />
      </section>
    </main>
  );
}
