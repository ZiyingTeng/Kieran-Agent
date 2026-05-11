/**
 * Group Store - Manages group chat state
 */

import { create } from 'zustand';
import type { Group } from '@/types';

interface GroupState {
  groups: Group[];
  selectedGroupId: string | null;
  isGroupChat: boolean;
  mentionedGirlfriendIds: string[];
  setGroups: (groups: Group[]) => void;
  addGroup: (group: Group) => void;
  removeGroup: (groupId: string) => void;
  setSelectedGroup: (groupId: string | null) => void;
  setIsGroupChat: (isGroupChat: boolean) => void;
  addMentionedGirlfriend: (girlfriendId: string) => void;
  removeMentionedGirlfriend: (girlfriendId: string) => void;
  clearMentionedGirlfriends: () => void;
  getSelectedGroup: () => Group | undefined;
  getGroupById: (groupId: string) => Group | undefined;
  isMentioned: (girlfriendId: string) => boolean;
}

export const useGroupStore = create<GroupState>((set, get) => ({
  groups: [],
  selectedGroupId: null,
  isGroupChat: false,
  mentionedGirlfriendIds: [],

  setGroups: (groups) => set({ groups }),

  addGroup: (group) =>
    set((state) => ({ groups: [...state.groups, group] })),

  removeGroup: (groupId) =>
    set((state) => ({
      groups: state.groups.filter((g) => g.group_id !== groupId),
      selectedGroupId:
        state.selectedGroupId === groupId ? null : state.selectedGroupId,
      isGroupChat:
        state.selectedGroupId === groupId ? false : state.isGroupChat,
    })),

  setSelectedGroup: (groupId) =>
    set({
      selectedGroupId: groupId,
      isGroupChat: groupId !== null,
      mentionedGirlfriendIds: [], // Clear mentions when switching groups
    }),

  setIsGroupChat: (isGroupChat) => set({ isGroupChat }),

  addMentionedGirlfriend: (girlfriendId) =>
    set((state) => ({
      mentionedGirlfriendIds: state.mentionedGirlfriendIds.includes(girlfriendId)
        ? state.mentionedGirlfriendIds
        : [...state.mentionedGirlfriendIds, girlfriendId],
    })),

  removeMentionedGirlfriend: (girlfriendId) =>
    set((state) => ({
      mentionedGirlfriendIds: state.mentionedGirlfriendIds.filter(
        (id) => id !== girlfriendId
      ),
    })),

  clearMentionedGirlfriends: () => set({ mentionedGirlfriendIds: [] }),

  getSelectedGroup: () => {
    const state = get();
    return state.groups.find((g) => g.group_id === state.selectedGroupId);
  },

  getGroupById: (groupId) => {
    const state = get();
    return state.groups.find((g) => g.group_id === groupId);
  },

  isMentioned: (girlfriendId) => {
    const state = get();
    return state.mentionedGirlfriendIds.includes(girlfriendId);
  },
}));
