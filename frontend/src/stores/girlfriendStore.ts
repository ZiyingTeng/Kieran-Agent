/**
 * Girlfriend Store - Manages girlfriend/role list
 */

import { create } from 'zustand';
import type { Girlfriend } from '@/types';

interface GirlfriendState {
  girlfriends: Girlfriend[];
  systemGirlfriends: Girlfriend[];
  customGirlfriends: Girlfriend[];
  selectedGirlfriendId: string | null;
  setGirlfriends: (girlfriends: Girlfriend[]) => void;
  addGirlfriend: (girlfriend: Girlfriend) => void;
  updateGirlfriend: (id: string, updates: Partial<Girlfriend>) => void;
  removeGirlfriend: (id: string) => void;
  setSelectedGirlfriend: (id: string | null) => void;
  getSelectedGirlfriend: () => Girlfriend | undefined;
  getGirlfriendById: (id: string) => Girlfriend | undefined;
}

export const useGirlfriendStore = create<GirlfriendState>((set, get) => ({
  girlfriends: [],
  systemGirlfriends: [],
  customGirlfriends: [],
  selectedGirlfriendId: null,

  setGirlfriends: (girlfriends) =>
    set({
      girlfriends,
      systemGirlfriends: girlfriends.filter((g) => g.is_system),
      customGirlfriends: girlfriends.filter((g) => !g.is_system),
    }),

  addGirlfriend: (girlfriend) =>
    set((state) => {
      const newGirlfriends = [...state.girlfriends, girlfriend];
      return {
        girlfriends: newGirlfriends,
        systemGirlfriends: newGirlfriends.filter((g) => g.is_system),
        customGirlfriends: newGirlfriends.filter((g) => !g.is_system),
      };
    }),

  updateGirlfriend: (id, updates) =>
    set((state) => {
      const newGirlfriends = state.girlfriends.map((g) =>
        g.girlfriend_id === id ? { ...g, ...updates } : g
      );
      return {
        girlfriends: newGirlfriends,
        systemGirlfriends: newGirlfriends.filter((g) => g.is_system),
        customGirlfriends: newGirlfriends.filter((g) => !g.is_system),
      };
    }),

  removeGirlfriend: (id) =>
    set((state) => {
      const newGirlfriends = state.girlfriends.filter((g) => g.girlfriend_id !== id);
      return {
        girlfriends: newGirlfriends,
        systemGirlfriends: newGirlfriends.filter((g) => g.is_system),
        customGirlfriends: newGirlfriends.filter((g) => !g.is_system),
        selectedGirlfriendId:
          state.selectedGirlfriendId === id ? null : state.selectedGirlfriendId,
      };
    }),

  setSelectedGirlfriend: (id) => set({ selectedGirlfriendId: id }),

  getSelectedGirlfriend: () => {
    const state = get();
    return state.girlfriends.find((g) => g.girlfriend_id === state.selectedGirlfriendId);
  },

  getGirlfriendById: (id) => {
    const state = get();
    return state.girlfriends.find((g) => g.girlfriend_id === id);
  },
}));
