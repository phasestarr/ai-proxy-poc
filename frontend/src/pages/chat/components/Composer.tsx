import { useLayoutEffect, useRef } from "react";
import type { FormEvent, RefObject } from "react";

import type { ChatSelection } from "../../../chat/api";
import type { ChatModelOption, ChatToolOption } from "../../../chat/api/modelApi";

type ComposerProps = {
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
  isSending: boolean;
  modelMenuRef: RefObject<HTMLDivElement>;
  toolsMenuRef: RefObject<HTMLDivElement>;
  onLogout: () => Promise<void> | void;
  onPromptChange: (value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => Promise<void> | void;
  onModelMenuToggle: () => void;
  onToolsMenuToggle: () => void;
  onModelSelect: (modelId: string) => void;
  onToolToggle: (toolId: string) => void;
};

export default function Composer({
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
  isSending,
  modelMenuRef,
  toolsMenuRef,
  onLogout,
  onPromptChange,
  onSubmit,
  onModelMenuToggle,
  onToolsMenuToggle,
  onModelSelect,
  onToolToggle,
}: ComposerProps) {
  const inputRef = useRef<HTMLTextAreaElement | null>(null);
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

  return (
    <form className="composer" onSubmit={onSubmit}>
      <textarea
        className="composer-input"
        disabled={isSending}
        ref={inputRef}
        value={prompt}
        onChange={(event) => onPromptChange(event.target.value)}
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
            disabled={isSending || isModelsLoading || prompt.trim().length === 0 || !selectedModel?.available}
            type="submit"
          >
            {isSending ? "Streaming..." : "Send"}
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
