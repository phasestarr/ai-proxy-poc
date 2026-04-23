import { useEffect, useRef, useState } from "react";

import { fetchAvailableModels, getChatModelOption, type ChatModelOption } from "../../../chat/api/modelApi";

export function useChatModelSelection() {
  const [modelOptions, setModelOptions] = useState<ChatModelOption[]>([]);
  const [isModelsLoading, setIsModelsLoading] = useState(true);
  const [modelsError, setModelsError] = useState<string | null>(null);
  const [selectedModelId, setSelectedModelId] = useState<string | null>(null);
  const [selectedToolIds, setSelectedToolIds] = useState<string[]>([]);
  const [isModelMenuOpen, setIsModelMenuOpen] = useState(false);
  const [isToolsMenuOpen, setIsToolsMenuOpen] = useState(false);
  const modelMenuRef = useRef<HTMLDivElement | null>(null);
  const toolsMenuRef = useRef<HTMLDivElement | null>(null);

  const selectedModel = getChatModelOption(modelOptions, selectedModelId);
  const availableTools = (selectedModel?.toolOptions ?? []).filter((tool) => tool.available);
  const selectedTools = availableTools.filter((tool) => selectedToolIds.includes(tool.id));

  useEffect(() => {
    let cancelled = false;

    const loadModels = async () => {
      try {
        const nextModels = await fetchAvailableModels();
        if (cancelled) {
          return;
        }

        setModelOptions(nextModels);
        setModelsError(null);
        setSelectedModelId((current) => {
          const currentModel = getChatModelOption(nextModels, current);
          return currentModel?.available ? current ?? null : null;
        });
      } catch (error) {
        if (cancelled) {
          return;
        }

        const detail = error instanceof Error ? error.message : "Failed to load model options.";
        setModelOptions([]);
        setModelsError(detail);
        setSelectedModelId(null);
      } finally {
        if (!cancelled) {
          setIsModelsLoading(false);
        }
      }
    };

    void loadModels();

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!selectedModelId) {
      setSelectedToolIds([]);
      return;
    }

    if (!selectedModel) {
      if (modelOptions.length > 0) {
        setSelectedToolIds([]);
      }
      return;
    }

    setSelectedToolIds((current) =>
      current.filter((toolId) => selectedModel.toolOptions.some((tool) => tool.available && tool.id === toolId)),
    );
  }, [modelOptions.length, selectedModel, selectedModelId]);

  useEffect(() => {
    const handlePointerDown = (event: MouseEvent) => {
      const target = event.target;
      if (!(target instanceof Node)) {
        return;
      }

      if (modelMenuRef.current && !modelMenuRef.current.contains(target)) {
        setIsModelMenuOpen(false);
      }

      if (toolsMenuRef.current && !toolsMenuRef.current.contains(target)) {
        setIsToolsMenuOpen(false);
      }
    };

    document.addEventListener("mousedown", handlePointerDown);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
    };
  }, []);

  const handleModelSelect = (modelId: string) => {
    const nextModel = getChatModelOption(modelOptions, modelId);
    if (!nextModel?.available) {
      return;
    }

    setSelectedModelId(modelId);
    setSelectedToolIds([]);
    setIsModelMenuOpen(false);
    setIsToolsMenuOpen(false);
  };

  const handleToolToggle = (toolId: string) => {
    if (!availableTools.some((tool) => tool.id === toolId)) {
      return;
    }

    setSelectedToolIds((current) =>
      current.includes(toolId) ? current.filter((value) => value !== toolId) : [...current, toolId],
    );
  };

  const handleModelMenuToggle = () => {
    setIsModelMenuOpen((current) => !current);
    setIsToolsMenuOpen(false);
  };

  const handleToolsMenuToggle = () => {
    if (!selectedModel?.available || availableTools.length === 0) {
      return;
    }
    setIsToolsMenuOpen((current) => !current);
    setIsModelMenuOpen(false);
  };

  const resetModelSelection = () => {
    setSelectedModelId(null);
    setSelectedToolIds([]);
    setIsModelMenuOpen(false);
    setIsToolsMenuOpen(false);
  };

  return {
    modelOptions,
    isModelsLoading,
    modelsError,
    selectedModel,
    selectedModelId,
    selectedToolIds,
    selectedTools,
    availableTools,
    isModelMenuOpen,
    isToolsMenuOpen,
    modelMenuRef,
    toolsMenuRef,
    setSelectedModelId,
    setSelectedToolIds,
    handleModelSelect,
    handleToolToggle,
    handleModelMenuToggle,
    handleToolsMenuToggle,
    resetModelSelection,
  };
}
