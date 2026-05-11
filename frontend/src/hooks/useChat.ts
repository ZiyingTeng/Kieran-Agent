/**
 * useChat - Custom hook for chat functionality
 */

import { useCallback, useEffect } from 'react';
import { useChatStore } from '@/stores/chatStore';
import { useUserStore } from '@/stores/userStore';
import { useGirlfriendStore } from '@/stores/girlfriendStore';
import { useGroupStore } from '@/stores/groupStore';
import { useModelStore } from '@/stores/modelStore';
import { sendPrivateMessage, sendGroupMessage, getHistory } from '@/api/chat';
import type { Message } from '@/types';
import { MessageRole, type MessageRoleValue } from '@/utils/constants';

interface UseChatReturn {
  messages: Message[];
  isLoading: boolean;
  isStreaming: boolean;
  sendMessage: (content: string) => Promise<void>;
  regenerateMessage: (messageId: string) => Promise<void>;
  editMessage: (messageId: string, newContent: string) => Promise<void>;
  clearHistory: () => void;
  loadHistory: () => Promise<void>;
}

export function useChat(): UseChatReturn {
  const { currentUserId } = useUserStore();
  const { getSelectedGirlfriend } = useGirlfriendStore();
  const { getSelectedGroup } = useGroupStore();
  const { getCurrentModel, getSettings } = useModelStore();

  const {
    getCurrentMessages,
    currentChatId,
    chatType,
    addMessage,
    updateMessage,
    clearMessages,
    setIsLoading,
    setIsStreaming,
    getCurrentConversation,
  } = useChatStore();

  const generateMessageId = () => `msg_${Date.now()}_${Math.random().toString(36).substring(2, 11)}`;

  const sendMessage = useCallback(
    async (content: string, options?: { retry?: boolean; messageId?: string; skipUserMsg?: boolean }) => {
      if (!content.trim() || !currentChatId) return;

      // 重新生成时不重复添加用户消息
      if (!options?.skipUserMsg) {
        const userMsg: Message = {
          msg_id: generateMessageId(),
          role: MessageRole.USER,
          content,
          timestamp: new Date().toISOString(),
        };
        addMessage(currentChatId, userMsg);
      }
      setIsLoading(currentChatId, true);

      try {
        if (chatType === 'private') {
          // Private chat
          const girlfriend = getSelectedGirlfriend();
          if (!girlfriend) return;

          const modelSettings = getSettings();
          const selectedModel = getCurrentModel();

          const request: any = {
            userId: currentUserId,
            expertId: girlfriend.girlfriend_id,
            mes: content,
            source: '0',
          };

          // 重新生成时传 retry 标记
          if (options?.retry) {
            request.retry = true;
            if (options.messageId) {
              request.messageId = options.messageId;
            }
          }

          if (selectedModel && modelSettings.selectedModel) {
            request.modelName = modelSettings.selectedModel;
            if (modelSettings.customApiPath) {
              request.apiPath = modelSettings.customApiPath;
            }
          }

          const response = await sendPrivateMessage(request);

          if (response.success && response.content) {
            const assistantMsg: Message = {
              msg_id: generateMessageId(),
              role: MessageRole.ASSISTANT,
              content: response.content,
              timestamp: response.timestamp || new Date().toISOString(),
              girl_name: girlfriend.name,
              emotion: response.emotion,  // 保存情绪标签
            };
            addMessage(currentChatId, assistantMsg);
          }
        } else {
          // Group chat
          const group = getSelectedGroup();
          if (!group) return;

          const { mentionedGirlfriendIds } = useGroupStore.getState();

          setIsStreaming(currentChatId, true);

          await sendGroupMessage(
            group.group_id,
            content,
            currentUserId,
            mentionedGirlfriendIds,
            // onMessage
            (event: unknown) => {
              if (event && typeof event === 'object') {
                const e = event as Record<string, unknown>;
                if ('response' in e || 'name' in e || 'girlfriend_name' in e) {
                  const name = (e.name || e.girlfriend_name) as string;
                  const response = e.response as string;
                  const timestamp = (e.message as { timestamp?: string })?.timestamp || new Date().toISOString();
                  const emotion = (e.emotion as string) || undefined;  // 支持情绪标签

                  const assistantMsg: Message = {
                    msg_id: generateMessageId(),
                    role: MessageRole.ASSISTANT,
                    content: response,
                    timestamp,
                    girl_name: name,
                    emotion,  // 保存情绪标签
                  };
                  addMessage(currentChatId, assistantMsg);
                }
              }
            },
            // onComplete
            () => {
              setIsStreaming(currentChatId, false);
            },
            // onError
            (error) => {
              setIsStreaming(currentChatId, false);
              console.error('SSE error:', error);
            }
          );
        }
      } catch (error) {
        console.error('Failed to send message:', error);
      } finally {
        setIsLoading(currentChatId, false);
      }
    },
    [
      currentChatId,
      chatType,
      currentUserId,
      addMessage,
      setIsLoading,
      setIsStreaming,
      getSelectedGirlfriend,
      getSelectedGroup,
      getCurrentModel,
      getSettings,
    ]
  );

  const regenerateMessage = useCallback(
    async (messageId: string) => {
      const messages = getCurrentMessages();
      const messageIndex = messages.findIndex((m) => m.msg_id === messageId);
      if (messageIndex === -1) return;

      // Remove this message and all messages after it
      const newMessages = messages.slice(0, messageIndex);
      clearMessages(currentChatId || '');
      newMessages.forEach((msg) => addMessage(currentChatId || '', msg));

      // Find the last user message before the removed AI message
      const lastUserMessage = [...newMessages]
        .reverse()
        .find((m) => m.role === MessageRole.USER);

      if (lastUserMessage) {
        // 带 retry 标记重新发送，让后端清理旧回复的记忆
        await sendMessage(lastUserMessage.content, {
          retry: true,
          messageId,
          skipUserMsg: true,  // 用户消息已在 newMessages 中，不重复添加
        });
      }
    },
    [getCurrentMessages, clearMessages, addMessage, currentChatId, sendMessage]
  );

  const editMessage = useCallback(
    async (messageId: string, newContent: string) => {
      updateMessage(currentChatId || '', messageId, { content: newContent });
    },
    [currentChatId, updateMessage]
  );

  const clearHistory = useCallback(() => {
    if (currentChatId) {
      clearMessages(currentChatId);
    }
  }, [currentChatId, clearMessages]);

  // Load history from backend when user or chat changes
  useEffect(() => {
    const loadHistoryFromBackend = async () => {
      if (!currentChatId || !currentUserId) return;

      // Only load history for private chats
      if (chatType !== 'private') return;

      const girlfriend = getSelectedGirlfriend();
      if (!girlfriend) return;

      try {
        const response = await getHistory(currentUserId, girlfriend.girlfriend_id);

        if (response.success && response.history) {
          // Convert backend history format to Message format
          const messages: Message[] = response.history.map((msg, index) => ({
            msg_id: `history_${currentUserId}_${girlfriend.girlfriend_id}_${index}`,
            role: msg.role as MessageRoleValue,
            content: msg.content,
            timestamp: msg.timestamp || new Date().toISOString(),
            girl_name: msg.name || girlfriend.name,
            emotion: msg.emotion,  // 保存情绪标签（如果有）
          }));

          // Load into store (will only load if user_id matches)
          const { loadHistoryFromBackend: loadHist, setCurrentUser } = useChatStore.getState();
          setCurrentUser(currentUserId);
          loadHist(currentUserId, girlfriend.girlfriend_id, messages);
        }
      } catch (error) {
        console.error('Failed to load history:', error);
      }
    };

    loadHistoryFromBackend();
  }, [currentUserId, currentChatId, chatType, getSelectedGirlfriend]);

  const loadHistory = useCallback(async () => {
    if (!currentChatId || !currentUserId) return;

    if (chatType !== 'private') return;

    const girlfriend = getSelectedGirlfriend();
    if (!girlfriend) return;

    try {
      const response = await getHistory(currentUserId, girlfriend.girlfriend_id);

      if (response.success && response.history) {
        const messages: Message[] = response.history.map((msg, index) => ({
          msg_id: `history_${currentUserId}_${girlfriend.girlfriend_id}_${index}`,
          role: msg.role as MessageRoleValue,
          content: msg.content,
          timestamp: msg.timestamp || new Date().toISOString(),
          girl_name: msg.name || girlfriend.name,
          emotion: msg.emotion,  // 保存情绪标签（如果有）
        }));

        const { loadHistoryFromBackend: loadHist, setCurrentUser } = useChatStore.getState();
        setCurrentUser(currentUserId);
        loadHist(currentUserId, girlfriend.girlfriend_id, messages);
      }
    } catch (error) {
      console.error('Failed to load history:', error);
    }
  }, [currentChatId, currentUserId, chatType, getSelectedGirlfriend]);

  return {
    messages: getCurrentMessages(),
    isLoading: getCurrentConversation()?.isLoading || false,
    isStreaming: getCurrentConversation()?.isStreaming || false,
    sendMessage,
    regenerateMessage,
    editMessage,
    clearHistory,
    loadHistory,
  };
}
