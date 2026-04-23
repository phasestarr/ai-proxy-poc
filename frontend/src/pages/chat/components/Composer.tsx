import type { FormEvent, RefObject } from "react";

import type { ChatSelection } from "../../../chat/api";
import type { ChatModelOption, ChatToolOption } from "../../../chat/api/modelApi";

type ComposerProps = {
  prompt: string;
  modelsError: string | null;
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
  onPromptChange,
  onSubmit,
  onModelMenuToggle,
  onToolsMenuToggle,
  onModelSelect,
  onToolToggle,
}: ComposerProps) {
  const toolsButtonLabel =
    selectedTools.length > 0 ? `Tools: ${selectedTools.map((tool) => tool.label).join(", ")}` : "Tools: None";
  const isToolsButtonDisabled = !selectedModel?.available || availableTools.length === 0;

  return (
    <form className="composer" onSubmit={onSubmit}>
      <textarea
        className="composer-input"
        value={prompt}
        onChange={(event) => onPromptChange(event.target.value)}
        placeholder="Type your prompt..."
        rows={3}
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
        <button
          className="composer-send-button"
          disabled={isSending || isModelsLoading || prompt.trim().length === 0 || !selectedModel?.available}
          type="submit"
        >
          {isSending ? "Streaming..." : "Send"}
        </button>
      </div>
      {modelsError ? <p className="chat-error">Error: {modelsError}</p> : null}
    </form>
  );
}

export function buildChatSelection(selectedModel: ChatModelOption | undefined, selectedToolIds: string[]): ChatSelection {
  return {
    modelId: selectedModel?.id ?? null,
    toolIds: selectedToolIds,
  };
}

