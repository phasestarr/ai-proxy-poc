import { ClipboardEvent, FormEvent, startTransition, useEffect, useRef, useState } from "react";

import { getRandomWelcomeText } from "../config/chatContent";
import { AuthenticationRequiredError, SessionConflictError } from "../auth/authErrors";
import type { AuthSession, SessionConflictInfo } from "../auth/authTypes";
import {
  createChatDraft,
  deleteChatFile,
  deleteChatHistory,
  fetchChatHistories,
  fetchChatHistory,
  pinChatHistory,
  renameChatHistory,
  streamChatReply,
  updateChatFile,
  uploadChatFile,
  type ChatAttachmentLimits,
  type ChatDraft,
  type ChatHistoryFile,
  type ChatHistory,
  type ChatHistorySummary,
  unpinChatHistory,
} from "../chat/api";
import AttachmentRail from "./chat/components/AttachmentRail";
import Composer, { buildChatSelection } from "./chat/components/Composer";
import ImagePreviewModal from "./chat/components/ImagePreviewModal";
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
  toggleAssistantLatex,
  toggleAssistantMarkdown,
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

type QueuedUpload = {
  id: string;
  file: File;
};

const APP_NAME = "ver. 0.5.3-pre-Isotope";
const PASTED_IMAGE_MIME_TYPES = new Set(["image/png", "image/jpeg"]);

export default function ChatPage({ session, onLogout, onSessionExpired, onSessionConflict }: ChatPageProps) {
  const [prompt, setPrompt] = useState("");
  const [messages, setMessages] = useState<TranscriptMessage[]>([]);
  const [isSending, setIsSending] = useState(false);
  const [activeChatHistoryId, setActiveChatHistoryId] = useState<string | null>(null);
  const [activeDraft, setActiveDraft] = useState<ChatDraft | null>(null);
  const [activeFiles, setActiveFiles] = useState<ChatHistoryFile[]>([]);
  const [attachmentLimits, setAttachmentLimits] = useState<ChatAttachmentLimits | null>(null);
  const [historySummaries, setHistorySummaries] = useState<ChatHistorySummary[]>([]);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [sendError, setSendError] = useState<string | null>(null);
  const [attachmentError, setAttachmentError] = useState<string | null>(null);
  const [isHistoryLoading, setIsHistoryLoading] = useState(true);
  const [loadingHistoryId, setLoadingHistoryId] = useState<string | null>(null);
  const [deletingHistoryId, setDeletingHistoryId] = useState<string | null>(null);
  const [updatingHistoryId, setUpdatingHistoryId] = useState<string | null>(null);
  const [deletingFileId, setDeletingFileId] = useState<string | null>(null);
  const [updatingFileId, setUpdatingFileId] = useState<string | null>(null);
  const [uploadQueue, setUploadQueue] = useState<QueuedUpload[]>([]);
  const [activeUpload, setActiveUpload] = useState<QueuedUpload | null>(null);
  const [welcomeText, setWelcomeText] = useState(() => getRandomWelcomeText());
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [isAttachmentRailOpen, setIsAttachmentRailOpen] = useState(true);
  const [previewingFile, setPreviewingFile] = useState<ChatHistoryFile | null>(null);
  const nextMessageIdRef = useRef(1);
  const nextUploadIdRef = useRef(1);
  const activeChatHistoryIdRef = useRef<string | null>(null);
  const activeDraftChatIdRef = useRef<string | null>(null);
  const isMountedRef = useRef(true);
  const models = useChatModelSelection();
  const autoScroll = useConversationAutoScroll(messages);

  const hasStarted = messages.length > 0;
  const chatSelection = buildChatSelection(models.selectedModel, models.selectedToolIds);
  const isUploadingFile = activeUpload !== null;
  const activeHistorySummary = activeChatHistoryId
    ? historySummaries.find((history) => history.id === activeChatHistoryId) ?? null
    : null;
  const serverInteractionState = activeHistorySummary?.interactionState ?? activeDraft?.interactionState ?? "ready";
  const serverBusyReason = activeHistorySummary?.busyReason ?? activeDraft?.busyReason ?? null;
  const isServerConversationBusy =
    Boolean(activeChatHistoryId || activeDraft?.draftChatId) && serverInteractionState !== "ready";
  const isLocalConversationBusy =
    isSending || isUploadingFile || uploadQueue.length > 0 || Boolean(deletingFileId) || Boolean(updatingFileId);
  const isConversationBusy =
    isLocalConversationBusy || isServerConversationBusy;
  const isUploadActionBlocked =
    isSending || Boolean(deletingFileId) || (isServerConversationBusy && !isUploadingFile && uploadQueue.length === 0);
  const isDeleteActionBlocked = isLocalConversationBusy;
  const userAttachmentCount = historySummaries.reduce((sum, history) => sum + history.attachmentCount, 0);
  const attachmentFooterPrimary = `${activeFiles.length}/${attachmentLimits?.maxFilesPerHistory ?? "-"} files`;
  const attachmentFooterSecondary = `${userAttachmentCount}/${attachmentLimits?.maxFilesPerUser ?? "-"} total`;
  const attachmentStatusText =
    activeUpload !== null
      ? uploadQueue.length > 0
        ? `Uploading file... ${uploadQueue.length} pending`
        : "Uploading file..."
      : uploadQueue.length > 0
      ? `${uploadQueue.length} files queued`
      : serverInteractionState === "validating" && serverBusyReason === "attach_file"
      ? "Uploading file..."
      : serverInteractionState === "validating"
      ? "Validating..."
      : null;
  const sendButtonLabel = serverInteractionState === "waiting" && !isUploadingFile && uploadQueue.length === 0
    ? "Streaming..."
    : "Validating...";

  useEffect(() => {
    activeChatHistoryIdRef.current = activeChatHistoryId;
    activeDraftChatIdRef.current = activeDraft?.draftChatId ?? null;
  }, [activeChatHistoryId, activeDraft]);

  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
    };
  }, []);

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

  const upsertHistorySummary = (summary: ChatHistorySummary) => {
    setHistorySummaries((current) => {
      const existingIndex = current.findIndex((history) => history.id === summary.id);
      if (existingIndex < 0) {
        return [summary, ...current];
      }

      return current.map((history, index) => (index === existingIndex ? summary : history));
    });
  };

  const resetConversationState = ({ resetModelSelection }: { resetModelSelection: boolean }) => {
    setActiveChatHistoryId(null);
    setActiveDraft(null);
    setActiveFiles([]);
    setPreviewingFile(null);
    setMessages([]);
    setPrompt("");
    setSendError(null);
    setAttachmentError(null);
    setUploadQueue([]);
    setActiveUpload(null);
    setWelcomeText(getRandomWelcomeText());
    nextMessageIdRef.current = 1;
    if (resetModelSelection) {
      models.resetModelSelection();
    }
    autoScroll.enableAutoScroll();
  };

  const applyLoadedHistory = (historyPayload: ChatHistory) => {
    const mapped = mapHistoryMessagesToTranscript(historyPayload.messages, models.modelOptions);
    const latestSelection = getLatestHistorySelection(historyPayload.messages);
    setActiveChatHistoryId(historyPayload.history.id);
    setActiveDraft(null);
    setActiveFiles(historyPayload.files);
    setPreviewingFile(null);
    setMessages(mapped.messages);
    setAttachmentLimits(historyPayload.attachmentLimits);
    setPrompt("");
    nextMessageIdRef.current = mapped.nextMessageId;
    upsertHistorySummary(historyPayload.history);
    if (historyPayload.messages.length > 0) {
      models.setSelectedModelId(latestSelection.modelId);
      models.setSelectedToolIds(latestSelection.toolIds);
    }
    autoScroll.enableAutoScroll();
  };

  const refreshHistorySummaries = async () => {
    try {
      const index = await fetchChatHistories();
      setHistorySummaries(index.histories);
      setAttachmentLimits(index.attachmentLimits);
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
    setAttachmentLimits(null);
    resetConversationState({ resetModelSelection: true });

    let cancelled = false;
    const loadHistories = async () => {
      try {
        const index = await fetchChatHistories();
        if (cancelled) {
          return;
        }
        setHistorySummaries(index.histories);
        setAttachmentLimits(index.attachmentLimits);
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
    if (isConversationBusy) {
      return;
    }

    resetConversationState({ resetModelSelection: true });
  };

  const handleSelectHistory = async (historyId: string) => {
    if (isConversationBusy || loadingHistoryId || historyId === activeChatHistoryId) {
      return;
    }

    setLoadingHistoryId(historyId);
    setHistoryError(null);
    setSendError(null);
    setAttachmentError(null);
    try {
      const history = await fetchChatHistory(historyId);
      applyLoadedHistory(history);
    } catch (error) {
      handleRecoverableError(error, "Failed to load chat history.");
    } finally {
      setLoadingHistoryId(null);
    }
  };

  const handleDeleteHistory = async (historyId: string) => {
    if (isDeleteActionBlocked || deletingHistoryId || updatingHistoryId) {
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

  const runQueuedUpload = async (file: File) => {
    if (isSending || deletingFileId) {
      return;
    }

    setAttachmentError(null);
    setHistoryError(null);
    try {
      let targetDraftChatId = activeDraftChatIdRef.current;
      if (!activeChatHistoryIdRef.current && !targetDraftChatId) {
        const createdDraft = await createChatDraft();
        targetDraftChatId = createdDraft.draftChatId;
        setActiveDraft(createdDraft);
      }

      const result = await uploadChatFile(file, activeChatHistoryIdRef.current, targetDraftChatId);
      setAttachmentLimits(result.attachmentLimits);
      if (result.history) {
        setActiveChatHistoryId(result.history.id);
        setActiveDraft(null);
        upsertHistorySummary(result.history);
      }
      setActiveFiles(result.files);
      await refreshHistorySummaries();
    } catch (error) {
      if (error instanceof AuthenticationRequiredError) {
        setUploadQueue([]);
        onSessionExpired();
        return;
      }

      if (error instanceof SessionConflictError) {
        setUploadQueue([]);
        onSessionConflict(error.conflict);
        return;
      }

      setAttachmentError(error instanceof Error ? error.message : "Failed to upload file.");
    }
  };

  const handleUploadFiles = (files: File[]) => {
    if (isUploadActionBlocked) {
      return;
    }

    setAttachmentError(null);
    setUploadQueue((current) => [
      ...current,
      ...files.map((file) => ({
        id: `upload-${nextUploadIdRef.current++}`,
        file,
      })),
    ]);
  };

  const handlePromptPaste = (event: ClipboardEvent<HTMLTextAreaElement>) => {
    const clipboardItems = Array.from(event.clipboardData?.items ?? []);
    const imageItem = clipboardItems.find(
      (item) => item.kind === "file" && PASTED_IMAGE_MIME_TYPES.has(item.type),
    );
    if (!imageItem) {
      return;
    }

    event.preventDefault();
    if (isUploadActionBlocked) {
      setAttachmentError("Files cannot be uploaded while this chat is busy.");
      return;
    }

    const pastedFile = imageItem.getAsFile();
    if (!pastedFile) {
      return;
    }

    setAttachmentError(null);
    handleUploadFiles([normalizePastedImageFile(pastedFile)]);
  };

  const handleDeleteFile = async (fileId: string) => {
    if (!activeChatHistoryId || isDeleteActionBlocked) {
      return;
    }

    setDeletingFileId(fileId);
    setAttachmentError(null);
    setHistoryError(null);
    try {
      const result = await deleteChatFile(activeChatHistoryId, fileId);
      setAttachmentLimits(result.attachmentLimits);
      if (result.deletedHistoryId) {
        resetConversationState({ resetModelSelection: false });
        setHistorySummaries((current) => current.filter((history) => history.id !== result.deletedHistoryId));
      } else {
        if (result.history) {
          setActiveChatHistoryId(result.history.id);
          upsertHistorySummary(result.history);
        }
        setActiveFiles(result.files);
      }
      await refreshHistorySummaries();
    } catch (error) {
      if (error instanceof AuthenticationRequiredError) {
        onSessionExpired();
        return;
      }

      if (error instanceof SessionConflictError) {
        onSessionConflict(error.conflict);
        return;
      }

      setAttachmentError(error instanceof Error ? error.message : "Failed to delete file.");
    } finally {
      setDeletingFileId(null);
    }
  };

  const handleToggleFileActive = async (fileId: string, isActive: boolean) => {
    if (!activeChatHistoryId || isDeleteActionBlocked) {
      return;
    }

    setUpdatingFileId(fileId);
    setAttachmentError(null);
    setHistoryError(null);
    try {
      const result = await updateChatFile(activeChatHistoryId, fileId, isActive);
      setAttachmentLimits(result.attachmentLimits);
      if (result.history) {
        setActiveChatHistoryId(result.history.id);
        upsertHistorySummary(result.history);
      }
      setActiveFiles(result.files);
      await refreshHistorySummaries();
    } catch (error) {
      if (error instanceof AuthenticationRequiredError) {
        onSessionExpired();
        return;
      }

      if (error instanceof SessionConflictError) {
        onSessionConflict(error.conflict);
        return;
      }

      setAttachmentError(error instanceof Error ? error.message : "Failed to update file state.");
    } finally {
      setUpdatingFileId(null);
    }
  };

  useEffect(() => {
    if (isSending || activeUpload || uploadQueue.length === 0) {
      return;
    }

    const [nextUpload, ...remaining] = uploadQueue;
    setUploadQueue(remaining);
    setActiveUpload(nextUpload);

    const processUpload = async () => {
      try {
        await runQueuedUpload(nextUpload.file);
      } finally {
        if (isMountedRef.current) {
          setActiveUpload((current) => (current?.id === nextUpload.id ? null : current));
        }
      }
    };

    void processUpload();
  }, [activeUpload, isSending, uploadQueue]);

  useEffect(() => {
    if (previewingFile === null) {
      return;
    }
    const nextMatch = activeFiles.find((file) => file.id === previewingFile.id && file.isActive && file.mimeType.startsWith("image/"));
    if (!nextMatch || !activeChatHistoryId) {
      setPreviewingFile(null);
    }
  }, [activeChatHistoryId, activeFiles, previewingFile]);

  const handleRenameHistory = async (historyId: string, title: string) => {
    if (isConversationBusy || deletingHistoryId || updatingHistoryId) {
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
    if (isConversationBusy || deletingHistoryId || updatingHistoryId) {
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
    if (!trimmedPrompt || isConversationBusy) {
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
    let targetHistoryId = activeChatHistoryId;
    let targetDraftChatId = activeDraft?.draftChatId ?? null;

    setSendError(null);
    setIsSending(true);
    autoScroll.enableAutoScroll();
    setPrompt("");
    setMessages((current) => [
      ...current,
      userMessage,
      assistantMessage,
    ]);

    try {
      if (!targetHistoryId && !targetDraftChatId) {
        const createdDraft = await createChatDraft();
        targetDraftChatId = createdDraft.draftChatId;
        setActiveDraft(createdDraft);
      }

      if (!targetHistoryId && !targetDraftChatId) {
        throw new Error("conversation id is required before streaming");
      }

      await streamChatReply({
        chatHistoryId: targetHistoryId,
        draftChatId: targetDraftChatId,
        messages: requestMessages,
        selection: chatSelection,
        onStart: (start) => {
          didStart = true;
          setActiveChatHistoryId(start.chatHistoryId);
          setActiveDraft(null);
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
      }

      if (!streamErrorHandled) {
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
      className={`chat-page ${hasStarted ? "chat-page--active" : "chat-page--idle"} ${isSidebarOpen ? "chat-page--sidebar-open" : "chat-page--sidebar-closed"} ${isAttachmentRailOpen ? "chat-page--attachment-open" : "chat-page--attachment-closed"}`}
    >
      <HistoryRail
        appName={APP_NAME}
        activeHistoryId={activeChatHistoryId}
        deletingHistoryId={deletingHistoryId}
        histories={historySummaries}
        historyError={historyError}
        isHistoryLoading={isHistoryLoading}
        isOpen={isSidebarOpen}
        isDeleteBlocked={isDeleteActionBlocked}
        isSending={isConversationBusy}
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
            onToggleLatex={(messageId) => {
              setMessages((current) => toggleAssistantLatex(current, messageId));
            }}
            onToggleMarkdown={(messageId) => {
              setMessages((current) => toggleAssistantMarkdown(current, messageId));
            }}
          />
        ) : null}

        <Composer
          activeFiles={activeFiles}
          activeHistoryId={activeChatHistoryId}
          availableTools={models.availableTools}
          isModelMenuOpen={models.isModelMenuOpen}
          isModelsLoading={models.isModelsLoading}
          isSending={isConversationBusy}
          sendButtonLabel={sendButtonLabel}
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
          onPromptPaste={handlePromptPaste}
          onPreviewImage={(file) => {
            setPreviewingFile(file);
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
      <AttachmentRail
        historyId={activeChatHistoryId}
        deletingFileId={deletingFileId}
        error={attachmentError}
        files={activeFiles}
        footerPrimary={attachmentFooterPrimary}
        footerSecondary={attachmentFooterSecondary}
        isDeleteBlocked={isDeleteActionBlocked}
        isOpen={isAttachmentRailOpen}
        isUploadBlocked={isUploadActionBlocked}
        isUploading={isUploadingFile}
        queuedUploadCount={uploadQueue.length}
        selectedProvider={models.selectedModel?.provider ?? null}
        statusText={attachmentStatusText}
        updatingFileId={updatingFileId}
        onDeleteFile={handleDeleteFile}
        onToggleFileActive={handleToggleFileActive}
        onToggle={() => {
          setIsAttachmentRailOpen((current) => !current);
        }}
        onUploadFiles={handleUploadFiles}
      />
      {previewingFile && activeChatHistoryId ? (
        <ImagePreviewModal
          file={previewingFile}
          historyId={activeChatHistoryId}
          onClose={() => {
            setPreviewingFile(null);
          }}
        />
      ) : null}
    </main>
  );
}

function normalizePastedImageFile(file: File): File {
  const normalizedMimeType = file.type === "image/jpg" ? "image/jpeg" : file.type;
  const extension = normalizedMimeType === "image/jpeg" ? "jpg" : "png";
  const hasUsableName = typeof file.name === "string" && file.name.trim().length > 0;
  const filename = hasUsableName ? file.name : `pasted-image-${Date.now()}.${extension}`;
  if (file.name === filename && file.type === normalizedMimeType) {
    return file;
  }
  return new File([file], filename, { type: normalizedMimeType, lastModified: Date.now() });
}
