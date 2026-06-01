import type { ChatHistoryFile } from "../../../chat/api";
import AttachmentPreview from "./AttachmentPreview";

export type PendingComposerUpload = {
  id: string;
  displayName: string;
  status: "processing" | "waiting";
};

type ComposerAttachmentStripProps = {
  historyId: string | null;
  files: ChatHistoryFile[];
  pendingUploads: PendingComposerUpload[];
  onPreviewImage: (file: ChatHistoryFile) => void;
};

export default function ComposerAttachmentStrip({
  historyId,
  files,
  pendingUploads,
  onPreviewImage,
}: ComposerAttachmentStripProps) {
  const activeFiles = files.filter((file) => file.isActive);

  if (activeFiles.length === 0 && pendingUploads.length === 0) {
    return null;
  }

  return (
    <div aria-label="Attached files" className="composer-attachment-strip">
      {activeFiles.map((file) => (
        file.mimeType.startsWith("image/") ? (
          <button
            className="composer-attachment-tile composer-attachment-tile--clickable"
            key={file.id}
            onClick={() => {
              onPreviewImage(file);
            }}
            title={file.displayName}
            type="button"
          >
            <AttachmentPreview
              className="composer-attachment-preview"
              file={file}
              historyId={historyId}
            />
          </button>
        ) : (
          <div
            className="composer-attachment-tile"
            key={file.id}
            title={file.displayName}
          >
            <AttachmentPreview
              className="composer-attachment-preview"
              file={file}
              historyId={historyId}
            />
          </div>
        )
      ))}
      {pendingUploads.map((upload) => (
        <div
          aria-label={`${upload.displayName} ${upload.status}`}
          className="composer-attachment-tile composer-attachment-tile--pending"
          key={upload.id}
          title={`${upload.displayName} - ${upload.status}`}
        >
          <div className="composer-attachment-preview composer-attachment-preview--pending">
            <span className="composer-attachment-pending-dot" />
            <span>{upload.status === "processing" ? "PROC" : "WAIT"}</span>
          </div>
        </div>
      ))}
    </div>
  );
}
