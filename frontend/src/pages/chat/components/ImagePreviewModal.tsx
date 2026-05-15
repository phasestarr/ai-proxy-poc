import type { ChatHistoryFile } from "../../../chat/api";
import { buildChatFileContentUrl } from "./AttachmentPreview";

type ImagePreviewModalProps = {
  file: ChatHistoryFile;
  historyId: string;
  onClose: () => void;
};

export default function ImagePreviewModal({ file, historyId, onClose }: ImagePreviewModalProps) {
  return (
    <button
      aria-label="Close image preview"
      className="image-preview-modal"
      onClick={onClose}
      type="button"
    >
      <img
        alt={file.displayName}
        className="image-preview-modal__image"
        src={buildChatFileContentUrl(historyId, file.id)}
      />
    </button>
  );
}
