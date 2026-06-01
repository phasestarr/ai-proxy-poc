import { useLayoutEffect, useRef, useState } from "react";
import type { ClipboardEvent, DragEvent, FormEvent, RefObject } from "react";

import type { ChatHistoryFile, ChatSelection } from "../../../chat/api";
import type { ChatModelOption, ChatToolOption } from "../../../chat/api/modelApi";
import ComposerAttachmentStrip, { type PendingComposerUpload } from "./ComposerAttachmentStrip";

type ComposerProps = {
  activeFiles: ChatHistoryFile[];
  activeHistoryId: string | null;
  pendingUploads: PendingComposerUpload[];
  prompt: string;
  modelsError: string | null;
  sendError: string | null;
  selectedModel: ChatModelOption | undefined;
  selectedModelId: string | null;
  selectedToolIds: string[];
  selectedTools: ChatToolOption[];
  availableTools: ChatToolOption[];
  modelOptions: ChatModelOption[];
  isModelsLoading: boolean;
  isModelMenuOpen: boolean;
  isToolsMenuOpen: boolean;
  isSendBlocked: boolean;
  isUploadBlocked: boolean;
  sendButtonLabel: string;
  modelMenuRef: RefObject<HTMLDivElement>;
  toolsMenuRef: RefObject<HTMLDivElement>;
  onLogout: () => Promise<void> | void;
  onPromptChange: (value: string) => void;
  onPromptPaste: (event: ClipboardEvent<HTMLTextAreaElement>) => void;
  onUploadFiles: (files: File[]) => Promise<void> | void;
  onPreviewImage: (file: ChatHistoryFile) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => Promise<void> | void;
  onModelMenuToggle: () => void;
  onToolsMenuToggle: () => void;
  onModelSelect: (modelId: string) => void;
  onToolToggle: (toolId: string) => void;
};

export default function Composer({
  activeFiles,
  activeHistoryId,
  pendingUploads,
  prompt,
  modelsError,
  sendError,
  selectedModel,
  selectedModelId,
  selectedToolIds,
  selectedTools,
  availableTools,
  modelOptions,
  isModelsLoading,
  isModelMenuOpen,
  isToolsMenuOpen,
  isSendBlocked,
  isUploadBlocked,
  sendButtonLabel,
  modelMenuRef,
  toolsMenuRef,
  onLogout,
  onPromptChange,
  onPromptPaste,
  onUploadFiles,
  onPreviewImage,
  onSubmit,
  onModelMenuToggle,
  onToolsMenuToggle,
  onModelSelect,
  onToolToggle,
}: ComposerProps) {
  const inputRef = useRef<HTMLTextAreaElement | null>(null);
  const dragDepthRef = useRef(0);
  const [isDraggingFiles, setIsDraggingFiles] = useState(false);
  const toolsButtonLabel =
    selectedTools.length > 0 ? `Tools: ${selectedTools.map((tool) => tool.label).join(", ")}` : "Tools: None";
  const isToolsButtonDisabled = !selectedModel?.available || availableTools.length === 0;

  useLayoutEffect(() => {
    const textarea = inputRef.current;
    if (!textarea) {
      return;
    }

    const maxHeight = Math.floor(window.innerHeight * 0.5);
    textarea.style.height = "0px";
    textarea.style.height = `${Math.min(textarea.scrollHeight, maxHeight)}px`;
  }, [prompt]);

  const handleDragEnter = (event: DragEvent<HTMLFormElement>) => {
    if (!containsFileDrag(event.dataTransfer)) {
      return;
    }
    event.preventDefault();
    dragDepthRef.current += 1;
    setIsDraggingFiles(true);
  };

  const handleDragOver = (event: DragEvent<HTMLFormElement>) => {
    if (!containsFileDrag(event.dataTransfer)) {
      return;
    }
    event.preventDefault();
    event.dataTransfer.dropEffect = isUploadBlocked ? "none" : "copy";
    setIsDraggingFiles(true);
  };

  const handleDragLeave = (event: DragEvent<HTMLFormElement>) => {
    if (!containsFileDrag(event.dataTransfer)) {
      return;
    }
    event.preventDefault();
    dragDepthRef.current = Math.max(0, dragDepthRef.current - 1);
    if (dragDepthRef.current === 0) {
      setIsDraggingFiles(false);
    }
  };

  const handleDrop = (event: DragEvent<HTMLFormElement>) => {
    if (!containsFileDrag(event.dataTransfer)) {
      return;
    }
    event.preventDefault();
    dragDepthRef.current = 0;
    setIsDraggingFiles(false);
    const files = Array.from(event.dataTransfer.files ?? []);
    if (files.length > 0) {
      void onUploadFiles(files);
    }
  };

  return (
    <form
      className={`composer ${isDraggingFiles ? "composer--dragging" : ""}`}
      onDragEnter={handleDragEnter}
      onDragLeave={handleDragLeave}
      onDragOver={handleDragOver}
      onDrop={handleDrop}
      onSubmit={onSubmit}
    >
      <ComposerAttachmentStrip
        files={activeFiles}
        historyId={activeHistoryId}
        pendingUploads={pendingUploads}
        onPreviewImage={onPreviewImage}
      />
      <textarea
        className="composer-input"
        ref={inputRef}
        value={prompt}
        onChange={(event) => onPromptChange(event.target.value)}
        onPaste={onPromptPaste}
        placeholder="Type your prompt..."
        rows={1}
      />
      <div className="composer-actions">
        <div className="composer-action-group">
          <div className="composer-action-menu" ref={modelMenuRef}>
            <button
              className="composer-action-button"
              aria-expanded={isModelMenuOpen}
              aria-haspopup="listbox"
              disabled={isModelsLoading || modelOptions.length === 0}
              onClick={onModelMenuToggle}
              type="button"
            >
              <span>{`Model: ${selectedModel?.label ?? "Select Model"}`}</span>
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
                    onClick={() => onModelSelect(option.id)}
                    role="option"
                    type="button"
                  >
                    <span>{option.label}</span>
                    {!option.available ? <span className="composer-option-status">PRIVATE</span> : null}
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
              onClick={onToolsMenuToggle}
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
                      onChange={() => onToolToggle(tool.id)}
                      type="checkbox"
                    />
                    <span>{tool.label}</span>
                  </label>
                ))}
              </div>
            ) : null}
          </div>
        </div>
        <div className="composer-submit-group">
          <button className="composer-logout-button" onClick={() => void onLogout()} type="button">
            Log out
          </button>
          <button
            className="composer-send-button"
            disabled={isSendBlocked || isModelsLoading || prompt.trim().length === 0 || !selectedModel?.available}
            type="submit"
          >
            {isSendBlocked ? sendButtonLabel : "Send"}
          </button>
        </div>
      </div>
      {modelsError ? <p className="chat-error">Error: {modelsError}</p> : null}
      {sendError ? <p className="chat-error">Error: {sendError}</p> : null}
    </form>
  );
}

export function buildChatSelection(selectedModel: ChatModelOption | undefined, selectedToolIds: string[]): ChatSelection {
  return {
    modelId: selectedModel?.id ?? null,
    toolIds: selectedToolIds,
  };
}

function containsFileDrag(dataTransfer: DataTransfer): boolean {
  return Array.from(dataTransfer.types ?? []).includes("Files");
}
