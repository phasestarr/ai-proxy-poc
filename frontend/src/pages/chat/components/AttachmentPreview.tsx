import { useState } from "react";

import type { ChatHistoryFile } from "../../../chat/api";

type AttachmentPreviewProps = {
  file: ChatHistoryFile;
  historyId: string | null;
  className?: string;
};

export default function AttachmentPreview({ file, historyId, className }: AttachmentPreviewProps) {
  const [didImageLoadFail, setDidImageLoadFail] = useState(false);
  const isImage = file.mimeType.startsWith("image/");
  const contentUrl = historyId ? buildChatFileContentUrl(historyId, file.id) : null;

  if (isImage && contentUrl && !didImageLoadFail) {
    return (
      <img
        alt={file.displayName}
        className={className}
        loading="lazy"
        onError={() => {
          setDidImageLoadFail(true);
        }}
        src={contentUrl}
      />
    );
  }

  return (
    <div className={className}>
      <span>{isImage ? "IMG" : "PDF"}</span>
    </div>
  );
}

export function buildChatFileContentUrl(historyId: string, fileId: string): string {
  return `/api/v1/chat/histories/${encodeURIComponent(historyId)}/files/${encodeURIComponent(fileId)}/content`;
}
