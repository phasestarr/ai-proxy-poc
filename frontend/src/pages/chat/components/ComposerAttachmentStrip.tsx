import type { ChatHistoryFile } from "../../../chat/api";
import AttachmentPreview from "./AttachmentPreview";

type ComposerAttachmentStripProps = {
  historyId: string | null;
  files: ChatHistoryFile[];
  onPreviewImage: (file: ChatHistoryFile) => void;
};

export default function ComposerAttachmentStrip({ historyId, files, onPreviewImage }: ComposerAttachmentStripProps) {
  const activeFiles = files.filter((file) => file.isActive);

  if (activeFiles.length === 0) {
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
    </div>
  );
}
