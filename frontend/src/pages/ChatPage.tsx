import { FormEvent, startTransition, useEffect, useRef, useState } from "react";

import { getRandomCompletionNote, getRandomWelcomeText } from "../config/chatContent";
import { AuthenticationRequiredError, SessionConflictError } from "../auth/authErrors";
import type { AuthSession, SessionConflictInfo } from "../auth/authTypes";
import {
  deleteChatHistory,
  fetchChatHistories,
  fetchChatHistory,
  streamChatReply,
  type ChatHistorySummary,
} from "../chat/api";
import ChatToolbar from "./chat/components/ChatToolbar";
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
  excludeFailedExchange,
  getLatestHistorySelection,
  mapHistoryMessagesToTranscript,
  removeExchange,
  type TranscriptMessage,
} from "./chat/state/transcript";
import "./chat/styles/chat.css";

type ChatPageProps = {
  session: AuthSession;
  onLogout: () => Promise<void> | void;
  onSessionExpired: () => void;
  onSessionConflict: (conflict: SessionConflictInfo) => void;
};

export default function ChatPage({ session, onLogout, onSessionExpired, onSessionConflict }: ChatPageProps) {
  const [prompt, setPrompt] = useState("");
  const [messages, setMessages] = useState<TranscriptMessage[]>([]);
  const [isSending, setIsSending] = useState(false);
  const [activeChatHistoryId, setActiveChatHistoryId] = useState<string | null>(null);
  const [historySummaries, setHistorySummaries] = useState<ChatHistorySummary[]>([]);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [isHistoryLoading, setIsHistoryLoading] = useState(true);
  const [loadingHistoryId, setLoadingHistoryId] = useState<string | null>(null);
  const [deletingHistoryId, setDeletingHistoryId] = useState<string | null>(null);
  const [welcomeText] = useState(() => getRandomWelcomeText());
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
    try {
      const history = await fetchChatHistory(historyId);
      const mapped = mapHistoryMessagesToTranscript(history.messages);
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
    if (isSending || deletingHistoryId) {
      return;
    }

    setDeletingHistoryId(historyId);
    setHistoryError(null);
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

    setPrompt("");
    setIsSending(true);
    autoScroll.enableAutoScroll();
    setMessages((current) => [
      ...current,
      userMessage,
      assistantMessage,
    ]);

    try {
      await streamChatReply({
        chatHistoryId: activeChatHistoryId,
        messages: requestMessages,
        selection: chatSelection,
        onStart: (start) => {
          setActiveChatHistoryId(start.chatHistoryId);
          void refreshHistorySummaries();
        },
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

      if (error instanceof SessionConflictError) {
        setMessages((current) => removeExchange(current, userMessageId, assistantMessageId));
        onSessionConflict(error.conflict);
        return;
      }

      const detail = error instanceof Error ? error.message : "unknown error";
      setMessages((current) => excludeFailedExchange(current, userMessageId, assistantMessageId, detail));
    } finally {
      setIsSending(false);
      void refreshHistorySummaries();
    }
  };

  return (
    <main className={`chat-page ${hasStarted ? "chat-page--active" : ""}`}>
      <HistoryRail
        activeHistoryId={activeChatHistoryId}
        deletingHistoryId={deletingHistoryId}
        histories={historySummaries}
        historyError={historyError}
        isHistoryLoading={isHistoryLoading}
        isSending={isSending}
        loadingHistoryId={loadingHistoryId}
        onDeleteHistory={handleDeleteHistory}
        onNewChat={handleNewChat}
        onSelectHistory={handleSelectHistory}
      />
      <section className="chat-shell">
        {!hasStarted ? (
          <section className="welcome-panel">
            <p className="welcome-eyebrow">Welcome</p>
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

        <ChatToolbar onLogout={onLogout} session={session} />

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
          onPromptChange={setPrompt}
          onSubmit={handleSubmit}
          onToolToggle={models.handleToolToggle}
          onToolsMenuToggle={models.handleToolsMenuToggle}
          prompt={prompt}
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
