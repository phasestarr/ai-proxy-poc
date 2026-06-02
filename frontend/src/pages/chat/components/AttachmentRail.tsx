import { useRef } from "react";

import type { ChatHistoryFile } from "../../../chat/api";
import AttachmentPreview from "./AttachmentPreview";

type AttachmentRailProps = {
  historyId: string | null;
  files: ChatHistoryFile[];
  selectedProvider: string | null;
  error: string | null;
  footerPrimary: string;
  footerSecondary: string;
  isOpen: boolean;
  isDeleteBlocked: boolean;
  isUploadBlocked: boolean;
  isUploading: boolean;
  queuedUploadCount: number;
  statusText: string | null;
  deletingFileId: string | null;
  updatingFileId: string | null;
  onToggle: () => void;
  onUploadFiles: (files: File[]) => Promise<void> | void;
  onDeleteFile: (fileId: string) => Promise<void> | void;
  onToggleFileActive: (fileId: string, isActive: boolean) => Promise<void> | void;
};

export default function AttachmentRail({
  historyId,
  files,
  selectedProvider,
  error,
  footerPrimary,
  footerSecondary,
  isOpen,
  isDeleteBlocked,
  isUploadBlocked,
  isUploading,
  queuedUploadCount,
  statusText,
  deletingFileId,
  updatingFileId,
  onToggle,
  onUploadFiles,
  onDeleteFile,
  onToggleFileActive,
}: AttachmentRailProps) {
  const inputRef = useRef<HTMLInputElement | null>(null);

  return (
    <aside
      aria-label="Chat attachments"
      className={`attachment-rail ${isOpen ? "attachment-rail--open" : "attachment-rail--closed"}`}
    >
      <div className="attachment-rail-header">
        {isOpen ? <p className="attachment-rail-title">Files</p> : null}
        <button
          aria-label={isOpen ? "Collapse files" : "Expand files"}
          className="attachment-rail-toggle"
          onClick={onToggle}
          type="button"
        >
          <span />
          <span />
        </button>
      </div>

      <div className="attachment-rail-body">
        <div className="attachment-primary-actions">
          <button
            className={`attachment-primary-button ${isOpen ? "attachment-primary-button--wide" : "attachment-primary-button--compact"}`}
            disabled={isUploadBlocked || deletingFileId !== null}
            onClick={() => {
              inputRef.current?.click();
            }}
            type="button"
          >
            <span className="attachment-primary-button-icon">+</span>
            {isOpen ? <span>Upload PDF/image</span> : null}
          </button>
          <input
            accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg"
            className="attachment-file-input"
            multiple
            onChange={(event) => {
              const nextFiles = Array.from(event.target.files ?? []);
              event.target.value = "";
              if (nextFiles.length === 0) {
                return;
              }
              void onUploadFiles(nextFiles);
            }}
            ref={inputRef}
            type="file"
          />
        </div>

        {isOpen ? (
          <>
            {statusText ? (
              <p className="attachment-queue-status">
                {statusText}
              </p>
            ) : null}
            {error ? <p className="attachment-error">{error}</p> : null}
            <div className="attachment-list">
              {files.length === 0 ? <p className="attachment-empty">No files attached.</p> : null}
              {files.map((file) => (
                <div className={`attachment-item ${file.isActive ? "attachment-item--active" : "attachment-item--inactive"}`} key={file.id}>
                  <AttachmentPreview
                    className={`attachment-item-preview ${file.isActive ? "" : "attachment-item-preview--inactive"}`.trim()}
                    file={file}
                    historyId={historyId}
                  />
                  <div className="attachment-item-copy">
                    <p className="attachment-item-title" title={file.displayName}>
                      {file.displayName}
                    </p>
                    <p className="attachment-item-meta">{buildAttachmentMeta(file, selectedProvider)}</p>
                  </div>
                  <div className="attachment-item-actions">
                    <button
                      className="attachment-toggle-button"
                      disabled={isDeleteBlocked || isUploading || deletingFileId !== null || updatingFileId !== null}
                      onClick={() => {
                        void onToggleFileActive(file.id, !file.isActive);
                      }}
                      type="button"
                    >
                      {updatingFileId === file.id ? "..." : file.isActive ? "-" : "+"}
                    </button>
                    <button
                      className="attachment-delete-button"
                      disabled={isDeleteBlocked || isUploading || deletingFileId !== null || updatingFileId !== null}
                      onClick={() => {
                        void onDeleteFile(file.id);
                      }}
                      type="button"
                    >
                      {deletingFileId === file.id ? "..." : "x"}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </>
        ) : null}
      </div>

      <div className="attachment-summary-slot">
        <p className="attachment-summary-label">{isOpen ? footerPrimary : footerPrimary.slice(0, 1)}</p>
        {isOpen ? <p className="attachment-summary-meta">{footerSecondary}</p> : null}
      </div>
    </aside>
  );
}

function formatAttachmentSize(byteSize: number): string {
  if (byteSize >= 1024 * 1024) {
    return `${(byteSize / (1024 * 1024)).toFixed(1)} MB`;
  }
  if (byteSize >= 1024) {
    return `${Math.round(byteSize / 1024)} KB`;
  }
  return `${byteSize} B`;
}

function buildAttachmentMeta(file: ChatHistoryFile, selectedProvider: string | null): string {
  const sizeLabel = formatAttachmentSize(file.byteSize);
  const tokenLabel = formatAttachmentTokens(file, selectedProvider);
  if (!tokenLabel) {
    return sizeLabel;
  }
  return `${sizeLabel} · ${tokenLabel}`;
}

function formatAttachmentTokens(file: ChatHistoryFile, selectedProvider: string | null): string | null {
  if (!selectedProvider) {
    return null;
  }

  if (selectedProvider === "openai" && file.tokenCounts.openai !== null) {
    return `${file.tokenCounts.openai.toLocaleString()} tok`;
  }
  if (selectedProvider === "anthropic" && file.tokenCounts.anthropic !== null) {
    return `${file.tokenCounts.anthropic.toLocaleString()} tok`;
  }
  if (selectedProvider === "vertex_ai" && file.tokenCounts.vertexAi !== null) {
    return `${file.tokenCounts.vertexAi.toLocaleString()} tok`;
  }
  return "N/A tok";
}
