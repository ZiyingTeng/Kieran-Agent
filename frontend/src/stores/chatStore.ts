/**
 * Chat Store - Manages chat state including messages and sessions
 */

import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { Message, ConversationState } from '@/types';
import { ChatType, type ChatTypeValue } from '@/types/chat';

interface ChatState {
  // Current chat context
  chatType: ChatTypeValue;
  currentChatId: string | null; // girlfriend_id or group_id
  currentChatName: string;
  currentUserId: string; // Track current user to avoid cross-user data leakage

  // Message storage per conversation
  conversations: Record<string, ConversationState>;

  // Actions
  setChatType: (type: ChatTypeValue) => void;
  setCurrentChat: (chatId: string | null, chatName: string) => void;
  setCurrentUser: (userId: string) => void;
  setConversation: (chatId: string, conversation: ConversationState) => void;
  addMessage: (chatId: string, message: Message) => void;
  updateMessage: (chatId: string, messageId: string, updates: Partial<Message>) => void;
  removeMessage: (chatId: string, messageId: string) => void;
  clearMessages: (chatId: string) => void;
  clearAllMessages: () => void;
  clearCurrentConversation: () => void;
  setIsLoading: (chatId: string, loading: boolean) => void;
  setIsStreaming: (chatId: string, streaming: boolean) => void;
  getMessages: (chatId: string) => Message[];
  getCurrentMessages: () => Message[];
  getCurrentConversation: () => ConversationState | undefined;
  loadHistoryFromBackend: (userId: string, expertId: string, messages: Message[]) => void;
}

export const useChatStore = create<ChatState>()(
  persist(
    (set, get) => ({
      chatType: ChatType.PRIVATE,
      currentChatId: null,
      currentChatName: '',
      currentUserId: '',
      conversations: {},

      setChatType: (type) => set({ chatType: type }),

      setCurrentChat: (chatId, chatName) =>
        set({
          currentChatId: chatId,
          currentChatName: chatName,
          // Initialize conversation if it doesn't exist
          conversations: {
            ...get().conversations,
            [chatId || '']: get().conversations[chatId || ''] || {
              messages: [],
              isLoading: false,
              isStreaming: false
            },
          },
        }),

      setCurrentUser: (userId) => {
        const state = get();
        if (state.currentUserId !== userId) {
          // User changed - clear all conversations to prevent cross-user data leakage
          set({
            currentUserId: userId,
            conversations: {},
            currentChatId: null,
            currentChatName: '',
          });
        }
      },

      setConversation: (chatId, conversation) =>
        set((state) => ({
          conversations: {
            ...state.conversations,
            [chatId]: conversation,
          },
        })),

      addMessage: (chatId, message) =>
        set((state) => {
          const conversation = state.conversations[chatId] || { messages: [] };
          return {
            conversations: {
              ...state.conversations,
              [chatId]: {
                ...conversation,
                messages: [...conversation.messages, message],
              },
            },
          };
        }),

      updateMessage: (chatId, messageId, updates) =>
        set((state) => {
          const conversation = state.conversations[chatId];
          if (!conversation) return state;

          return {
            conversations: {
              ...state.conversations,
              [chatId]: {
                ...conversation,
                messages: conversation.messages.map((msg) =>
                  msg.msg_id === messageId ? { ...msg, ...updates } : msg
                ),
              },
            },
          };
        }),

      removeMessage: (chatId, messageId) =>
        set((state) => {
          const conversation = state.conversations[chatId];
          if (!conversation) return state;

          return {
            conversations: {
              ...state.conversations,
              [chatId]: {
                ...conversation,
                messages: conversation.messages.filter((msg) => msg.msg_id !== messageId),
              },
            },
          };
        }),

      clearMessages: (chatId) =>
        set((state) => ({
          conversations: {
            ...state.conversations,
            [chatId]: { messages: [] },
          },
        })),

      clearAllMessages: () => set({ conversations: {} }),

      clearCurrentConversation: () => {
        const state = get();
        const chatId = state.currentChatId;
        if (chatId) {
          set({
            conversations: {
              ...state.conversations,
              [chatId]: {
                messages: [],
                isLoading: false,
                isStreaming: false
              },
            },
          });
        }
      },

      setIsLoading: (chatId, loading) =>
        set((state) => {
          const conversation = state.conversations[chatId] || { messages: [], isLoading: false, isStreaming: false };
          return {
            conversations: {
              ...state.conversations,
              [chatId]: {
                ...conversation,
                isLoading: loading,
              },
            },
          };
        }),

      setIsStreaming: (chatId, streaming) =>
        set((state) => {
          const conversation = state.conversations[chatId] || { messages: [], isLoading: false, isStreaming: false };
          return {
            conversations: {
              ...state.conversations,
              [chatId]: {
                ...conversation,
                isStreaming: streaming,
              },
            },
          };
        }),

      getMessages: (chatId) => {
        const state = get();
        return state.conversations[chatId]?.messages || [];
      },

      getCurrentMessages: () => {
        const state = get();
        const chatId = state.currentChatId || '';
        return state.conversations[chatId]?.messages || [];
      },

      getCurrentConversation: () => {
        const state = get();
        const chatId = state.currentChatId || '';
        return state.conversations[chatId];
      },

      loadHistoryFromBackend: (userId, expertId, messages) => {
        set((state) => {
          // Only load if user_id matches current user to prevent cross-user leakage
          if (state.currentUserId !== userId) {
            console.warn('Attempted to load history for different user - rejected');
            return state;
          }
          return {
            conversations: {
              ...state.conversations,
              [expertId]: { messages },
            },
          };
        });
      },
    }),
    {
      name: 'chat-storage',
      partialize: (state) => ({
        conversations: state.conversations,
        chatType: state.chatType,
        currentUserId: state.currentUserId, // Track user to invalidate cache
      }),
    }
  )
);
