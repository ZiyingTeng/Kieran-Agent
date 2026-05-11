/**
 * Model Store - Manages AI model settings
 */

import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { Model, ModelSettings } from '@/types';

interface ModelState {
  availableModels: Model[];
  currentModel: string;
  customApiPath: string;
  useAigirlApi: boolean;
  setAvailableModels: (models: Model[]) => void;
  setCurrentModel: (modelId: string) => void;
  setCustomApiPath: (path: string) => void;
  setUseAigirlApi: (use: boolean) => void;
  getSettings: () => ModelSettings;
  getModelById: (id: string) => Model | undefined;
  getCurrentModel: () => Model | undefined;
}

export const useModelStore = create<ModelState>()(
  persist(
    (set, get) => ({
      availableModels: [],
      currentModel: '',
      customApiPath: '',
      useAigirlApi: true,

      setAvailableModels: (models) => set({ availableModels: models }),

      setCurrentModel: (modelId) => set({ currentModel: modelId }),

      setCustomApiPath: (path) => set({ customApiPath: path }),

      setUseAigirlApi: (use) => set({ useAigirlApi: use }),

      getSettings: () => {
        const state = get();
        return {
          selectedModel: state.currentModel,
          customApiPath: state.customApiPath,
          useAigirlApi: state.useAigirlApi,
        };
      },

      getModelById: (id) => {
        const state = get();
        return state.availableModels.find((m) => m.id === id);
      },

      getCurrentModel: () => {
        const state = get();
        if (!state.currentModel) return undefined;
        return state.availableModels.find((m) => m.id === state.currentModel);
      },
    }),
    {
      name: 'model-storage',
    }
  )
);
