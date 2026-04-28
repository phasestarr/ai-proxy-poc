import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import type { AuthSession } from "../../../auth/authTypes";
import type { ChatHistorySummary } from "../../../chat/api";
import { formatHistoryTimestamp, getSessionLabel, getSessionTypeLabel } from "../formatters";

type HistoryRailProps = {
  appName: string;
  histories: ChatHistorySummary[];
  session: AuthSession;
  activeHistoryId: string | null;
  historyError: string | null;
  isHistoryLoading: boolean;
  isOpen: boolean;
  isSending: boolean;
  loadingHistoryId: string | null;
  deletingHistoryId: string | null;
  updatingHistoryId: string | null;
  onSidebarToggle: () => void;
  onNewChat: () => void;
  onSelectHistory: (historyId: string) => Promise<void> | void;
  onDeleteHistory: (historyId: string) => Promise<void> | void;
  onRenameHistory: (historyId: string, title: string) => Promise<void> | void;
  onTogglePinHistory: (historyId: string, isPinned: boolean) => Promise<void> | void;
};

export default function HistoryRail({
  appName,
  histories,
  session,
  activeHistoryId,
  historyError,
  isHistoryLoading,
  isOpen,
  isSending,
  loadingHistoryId,
  deletingHistoryId,
  updatingHistoryId,
  onSidebarToggle,
  onNewChat,
  onSelectHistory,
  onDeleteHistory,
  onRenameHistory,
  onTogglePinHistory,
}: HistoryRailProps) {
  const [openMenuHistoryId, setOpenMenuHistoryId] = useState<string | null>(null);
  const [renamingHistoryId, setRenamingHistoryId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const rootRef = useRef<HTMLElement | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);
  const menuButtonRefs = useRef(new Map<string, HTMLButtonElement>());
  const [menuPosition, setMenuPosition] = useState<{ top: number; left: number } | null>(null);

  useEffect(() => {
    if (!openMenuHistoryId) {
      setMenuPosition(null);
      return;
    }

    const updateMenuPosition = () => {
      const button = menuButtonRefs.current.get(openMenuHistoryId);
      if (!button) {
        setMenuPosition(null);
        return;
      }

      const rect = button.getBoundingClientRect();
      setMenuPosition({
        top: rect.bottom + 6,
        left: rect.right - 188,
      });
    };

    updateMenuPosition();
    window.addEventListener("resize", updateMenuPosition);
    window.addEventListener("scroll", updateMenuPosition, true);
    return () => {
      window.removeEventListener("resize", updateMenuPosition);
      window.removeEventListener("scroll", updateMenuPosition, true);
    };
  }, [openMenuHistoryId]);

  useEffect(() => {
    if (!isOpen) {
      setOpenMenuHistoryId(null);
      setRenamingHistoryId(null);
      setRenameValue("");
    }
  }, [isOpen]);

  useEffect(() => {
    const handlePointerDown = (event: MouseEvent) => {
      const target = event.target;
      if (!(target instanceof Node)) {
        return;
      }

      const clickedInsideRoot = rootRef.current?.contains(target) ?? false;
      const clickedInsideMenu = menuRef.current?.contains(target) ?? false;
      if (!clickedInsideRoot && !clickedInsideMenu) {
        setOpenMenuHistoryId(null);
        setRenamingHistoryId(null);
        setRenameValue("");
      }
    };

    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpenMenuHistoryId(null);
        setRenamingHistoryId(null);
        setRenameValue("");
      }
    };

    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("keydown", handleEscape);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("keydown", handleEscape);
    };
  }, []);

  const sessionLabel = getSessionLabel(session);
  const sessionTypeLabel = getSessionTypeLabel(session);

  return (
    <aside
      aria-label="Chat history"
      className={`history-rail ${isOpen ? "history-rail--open" : "history-rail--closed"}`}
      ref={rootRef}
    >
      <div className="history-rail-header">
        <div className="history-branding">
          {isOpen ? <p className="history-app-name">{appName}</p> : null}
        </div>
        <button
          aria-label={isOpen ? "Collapse sidebar" : "Expand sidebar"}
          className="history-sidebar-toggle"
          onClick={onSidebarToggle}
          type="button"
        >
          <span />
          <span />
        </button>
      </div>

      <div className="history-rail-body">
        <div className="history-primary-actions">
          <button
            className={`history-primary-button ${isOpen ? "history-primary-button--wide" : "history-primary-button--compact"}`}
            disabled={isSending}
            onClick={() => {
              setOpenMenuHistoryId(null);
              setRenamingHistoryId(null);
              setRenameValue("");
              onNewChat();
            }}
            type="button"
          >
            <span className="history-primary-button-icon">+</span>
            {isOpen ? <span>New chat</span> : null}
          </button>

          {isOpen ? (
            <button className="history-secondary-button" disabled type="button">
              <span className="history-secondary-button-icon">/</span>
              <span>Search chats</span>
            </button>
          ) : null}
        </div>

        {isOpen ? (
          <>
            {historyError ? <p className="history-error">{historyError}</p> : null}
            <div className="history-list">
              {isHistoryLoading ? <p className="history-empty">Loading histories...</p> : null}
              {!isHistoryLoading && histories.length === 0 ? <p className="history-empty">No saved chats yet.</p> : null}
              {histories.map((history) => {
                const isActive = history.id === activeHistoryId;
                const isLoading = history.id === loadingHistoryId;
                const isDeleting = history.id === deletingHistoryId;
                const isUpdating = history.id === updatingHistoryId;
                const isMenuOpen = history.id === openMenuHistoryId;
                const isPinned = history.pinOrder !== null;
                const isRenaming = history.id === renamingHistoryId;
                const metaParts = [
                  `${history.messageCount} messages`,
                  formatHistoryTimestamp(history.lastMessageAt ?? history.createdAt),
                ].filter(Boolean);
                return (
                  <div className={`history-item ${isActive ? "history-item--active" : ""}`} key={history.id}>
                    <button
                      className="history-select-button"
                      disabled={isSending || Boolean(loadingHistoryId) || isDeleting || isUpdating}
                      onClick={() => {
                        setOpenMenuHistoryId(null);
                        setRenamingHistoryId(null);
                        void onSelectHistory(history.id);
                      }}
                      type="button"
                    >
                      <span className="history-item-title-row">
                        {isPinned ? (
                          <span aria-hidden="true" className="history-item-pin">
                            📌
                          </span>
                        ) : null}
                        <span className="history-item-title">{isLoading ? "Loading..." : history.title}</span>
                      </span>
                      <span className="history-item-meta">{metaParts.join(" - ")}</span>
                    </button>
                    <div className="history-item-actions">
                      <button
                        aria-expanded={isMenuOpen}
                        aria-haspopup="menu"
                        aria-label={`Open actions for ${history.title}`}
                        className="history-menu-button"
                        disabled={isDeleting || isUpdating}
                        ref={(element) => {
                          if (element) {
                            menuButtonRefs.current.set(history.id, element);
                            return;
                          }
                          menuButtonRefs.current.delete(history.id);
                        }}
                        onClick={() => {
                          setRenamingHistoryId(null);
                          setOpenMenuHistoryId((current) => (current === history.id ? null : history.id));
                        }}
                        type="button"
                      >
                        ...
                      </button>
                    </div>
                    {isMenuOpen && menuPosition
                      ? createPortal(
                          <div
                            className="history-menu"
                            ref={menuRef}
                            role="menu"
                            style={{
                              top: `${Math.max(12, menuPosition.top)}px`,
                              left: `${Math.max(12, menuPosition.left)}px`,
                            }}
                          >
                            {isRenaming ? (
                              <form
                                className="history-rename-form"
                                onSubmit={(event) => {
                                  event.preventDefault();
                                  const nextTitle = renameValue.trim();
                                  if (!nextTitle) {
                                    return;
                                  }
                                  setOpenMenuHistoryId(null);
                                  setRenamingHistoryId(null);
                                  void onRenameHistory(history.id, nextTitle);
                                }}
                              >
                                <input
                                  autoFocus
                                  className="history-rename-input"
                                  maxLength={255}
                                  onChange={(event) => {
                                    setRenameValue(event.target.value);
                                  }}
                                  type="text"
                                  value={renameValue}
                                />
                                <div className="history-rename-actions">
                                  <button className="history-menu-item" type="submit">
                                    Save
                                  </button>
                                  <button
                                    className="history-menu-item"
                                    onClick={() => {
                                      setRenamingHistoryId(null);
                                      setRenameValue("");
                                    }}
                                    type="button"
                                  >
                                    Cancel
                                  </button>
                                </div>
                              </form>
                            ) : null}
                            {!isRenaming ? (
                              <>
                                <button
                                  className="history-menu-item"
                                  disabled={isSending || isDeleting || isUpdating}
                                  onClick={() => {
                                    setRenamingHistoryId(history.id);
                                    setRenameValue(history.title);
                                  }}
                                  role="menuitem"
                                  type="button"
                                >
                                  Rename
                                </button>
                                <button
                                  className="history-menu-item"
                                  disabled={isSending || isDeleting || isUpdating}
                                  onClick={() => {
                                    setOpenMenuHistoryId(null);
                                    void onTogglePinHistory(history.id, isPinned);
                                  }}
                                  role="menuitem"
                                  type="button"
                                >
                                  {isPinned ? "Unpin Chat" : "Pin Chat"}
                                </button>
                                <button className="history-menu-item" disabled role="menuitem" type="button">
                                  Remember this chat
                                </button>
                                <button
                                  className="history-menu-item history-menu-item--danger"
                                  disabled={isSending || isDeleting || isUpdating}
                                  onClick={() => {
                                    setOpenMenuHistoryId(null);
                                    void onDeleteHistory(history.id);
                                  }}
                                  role="menuitem"
                                  type="button"
                                >
                                  {isDeleting ? "Deleting..." : "Delete"}
                                </button>
                              </>
                            ) : null}
                          </div>,
                          document.body,
                        )
                      : null}
                  </div>
                );
              })}
            </div>
          </>
        ) : null}
      </div>

      <div className="history-session-slot">
        <p className="history-session-label">{isOpen ? sessionLabel : sessionLabel.slice(0, 1)}</p>
        {isOpen ? <p className="history-session-meta">{sessionTypeLabel}</p> : null}
      </div>
    </aside>
  );
}
