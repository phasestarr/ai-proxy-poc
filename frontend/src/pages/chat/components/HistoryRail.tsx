import type { ChatHistorySummary } from "../../../chat/api";
import { formatHistoryTimestamp } from "../formatters";

type HistoryRailProps = {
  histories: ChatHistorySummary[];
  activeHistoryId: string | null;
  historyError: string | null;
  isHistoryLoading: boolean;
  isSending: boolean;
  loadingHistoryId: string | null;
  deletingHistoryId: string | null;
  onNewChat: () => void;
  onSelectHistory: (historyId: string) => Promise<void> | void;
  onDeleteHistory: (historyId: string) => Promise<void> | void;
};

export default function HistoryRail({
  histories,
  activeHistoryId,
  historyError,
  isHistoryLoading,
  isSending,
  loadingHistoryId,
  deletingHistoryId,
  onNewChat,
  onSelectHistory,
  onDeleteHistory,
}: HistoryRailProps) {
  return (
    <aside className="history-rail" aria-label="Chat history">
      <div className="history-rail-header">
        <div>
          <p className="history-eyebrow">History</p>
          <h2 className="history-title">Chats</h2>
        </div>
        <button className="history-new-button" disabled={isSending} onClick={onNewChat} type="button">
          New
        </button>
      </div>
      {historyError ? <p className="history-error">{historyError}</p> : null}
      <div className="history-list">
        {isHistoryLoading ? <p className="history-empty">Loading histories...</p> : null}
        {!isHistoryLoading && histories.length === 0 ? <p className="history-empty">No saved chats yet.</p> : null}
        {histories.map((history) => {
          const isActive = history.id === activeHistoryId;
          const isLoading = history.id === loadingHistoryId;
          const isDeleting = history.id === deletingHistoryId;
          return (
            <div className={`history-item ${isActive ? "history-item--active" : ""}`} key={history.id}>
              <button
                className="history-select-button"
                disabled={isSending || Boolean(loadingHistoryId) || isDeleting}
                onClick={() => void onSelectHistory(history.id)}
                type="button"
              >
                <span className="history-item-title">{isLoading ? "Loading..." : history.title}</span>
                <span className="history-item-meta">
                  {`${history.messageCount} messages · ${formatHistoryTimestamp(history.updatedAt)}`}
                </span>
              </button>
              <button
                aria-label={`Delete ${history.title}`}
                className="history-delete-button"
                disabled={isSending || isDeleting}
                onClick={() => void onDeleteHistory(history.id)}
                type="button"
              >
                {isDeleting ? "..." : "×"}
              </button>
            </div>
          );
        })}
      </div>
    </aside>
  );
}

