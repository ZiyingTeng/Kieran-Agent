/**
 * ChatArea Component - Main chat interface with full integration
 * 支持 WebSocket 实时聊天和心跳问候推送
 */

import { useState, useRef, useEffect } from 'react';
import { useChat } from '@/hooks/useChat';
import { useWebSocket } from '@/hooks/useWebSocket';
import { useChatStore } from '@/stores/chatStore';
import { useUserStore } from '@/stores/userStore';
import { useGirlfriendStore } from '@/stores/girlfriendStore';
import { MessageList } from './MessageList';
import { MessageInput, type MessageInputRef } from './MessageInput';
import { Avatar } from '@/components/ui';
import type { DropdownItem } from '@/components/ui';
import { Dropdown } from '@/components/ui';
import { EditMessageModal } from '@/components/modal';
import { MentionModal } from '@/components/modal';
import * as api from '@/api';
import { toast } from '@/components/ui/Toast';

export function ChatArea() {
  const { currentUserId } = useUserStore();
  const { currentChatId, currentChatName, chatType, updateMessage, addMessage, setIsLoading } = useChatStore();
  const { getSelectedGirlfriend } = useGirlfriendStore();

  // WebSocket 相关状态
  const [enableWebSocket, setEnableWebSocket] = useState(true); // 默认启用 WebSocket

  const { messages, isLoading, isStreaming, sendMessage, regenerateMessage } = useChat();
  const ws = useWebSocket();
  const wsConnected = ws.isConnected; // 直接使用 WebSocket 的连接状态

  const [editingMessageId, setEditingMessageId] = useState<string | null>(null);
  const [editingMessage, setEditingMessage] = useState<any>(null);
  const [isMentionModalOpen, setIsMentionModalOpen] = useState(false);

  const messageInputRef = useRef<MessageInputRef>(null);

  // 当切换聊天对象时，自动连接 WebSocket
  useEffect(() => {
    if (enableWebSocket && currentUserId && currentChatId) {
      const girlfriend = getSelectedGirlfriend();
      if (girlfriend) {
        ws.connect(currentUserId, girlfriend.girlfriend_id);
      }
    }

    return () => {
      if (wsConnected && enableWebSocket) {
        // 只在WebSocket模式下断开连接
        // ws.disconnect(); // 注释掉自动断开，保持连接以供其他聊天使用
      }
    };
  }, [currentChatId, currentUserId, enableWebSocket, getSelectedGirlfriend, wsConnected]);

  const handleSendMessage = async (content: string) => {
    // 群聊走 HTTP SSE，WebSocket 仅用于私聊
    if (chatType === 'private' && enableWebSocket && wsConnected) {
      // 显示加载状态
      if (currentChatId) {
        setIsLoading(currentChatId, true);
      }

      // 添加用户消息到本地
      const userMsg = {
        msg_id: `msg_${Date.now()}`,
        role: 'user' as const,
        content,
        timestamp: new Date().toISOString(),
      };
      if (currentChatId) {
        addMessage(currentChatId, userMsg);
      }
      // 通过 WebSocket 发送
      ws.sendMessage(content);

      // WebSocket 模式下，设置一个超时来隐藏加载状态
      // 实际的响应会通过 WebSocket onmessage 接收
      if (currentChatId) {
        setTimeout(() => setIsLoading(currentChatId, false), 3000);
      }
    } else {
      // 否则使用 HTTP API
      await sendMessage(content);
    }
  };

  const handleToggleWebSocket = () => {
    if (enableWebSocket) {
      // 关闭 WebSocket
      ws.disconnect();
      setEnableWebSocket(false);
      toast.info('已切换到 HTTP 模式');
    } else {
      // 启用 WebSocket
      setEnableWebSocket(true);
      const girlfriend = getSelectedGirlfriend();
      if (girlfriend && currentUserId) {
        ws.connect(currentUserId, girlfriend.girlfriend_id);
      }
      toast.info('已切换到 WebSocket 模式');
    }
  };

  const handleEditMessage = (messageId: string) => {
    const message = messages.find((m) => m.msg_id === messageId);
    if (message) {
      setEditingMessageId(messageId);
      setEditingMessage(message);
    }
  };

  const handleSaveEdit = async (messageId: string, newContent: string) => {
    if (!currentChatId) return;

    const messageIndex = messages.findIndex((m) => m.msg_id === messageId);
    if (messageIndex === -1) return;

    const message = messages[messageIndex];
    updateMessage(currentChatId, messageId, { content: newContent });

    if (message.role === 'assistant') {
      const userMessage = messages[messageIndex - 1];
      if (userMessage && userMessage.role === 'user') {
        try {
          await api.updateHistory(
            currentUserId,
            currentChatId,
            userMessage.content,
            newContent
          );
          toast.success('消息已更新');
        } catch (error) {
          toast.error('更新失败');
        }
      }
    }

    setEditingMessageId(null);
    setEditingMessage(null);
  };

  const handleCloseEdit = () => {
    setEditingMessageId(null);
    setEditingMessage(null);
  };

  const handleRegenerate = async (messageId: string) => {
    await regenerateMessage(messageId);
  };

  const handleMentionSelect = (name: string) => {
    messageInputRef.current?.insertMention(name);
    setIsMentionModalOpen(false);
  };

  const menuItems: DropdownItem[] = [
    {
      id: 'websocket',
      label: enableWebSocket ? `🟢 WebSocket (${wsConnected ? '已连接' : '未连接'})` : '🔴 HTTP 模式',
      onClick: handleToggleWebSocket,
    },
    {
      id: 'clear',
      label: '清空聊天记录',
      icon: '🗑️',
      onClick: () => {
        if (currentChatId) {
          useChatStore.getState().clearMessages(currentChatId);
          toast.info('聊天记录已清空');
        }
      },
    },
  ];

  return (
    <div className="flex-1 flex flex-col bg-gray-50 overflow-hidden">
      {/* Chat Header */}
      <div className="flex items-center gap-3 px-5 py-4 bg-white border-b border-gray-100">
        <Avatar
          name={currentChatName || 'Chat'}
          size="lg"
          variant="primary"
        />
        <div className="flex-1">
          <h3 className="text-base font-semibold text-gray-900">
            {currentChatName || '选择聊天对象'}
          </h3>
          <p className="text-xs text-gray-500">
            {enableWebSocket && wsConnected ? '🟢 WebSocket 在线' :
             enableWebSocket ? '🟡 WebSocket 连接中...' :
             isStreaming ? '正在接收消息...' : '在线'}
          </p>
        </div>
        <Dropdown
          trigger={
            <button className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-full transition-colors">
              ⚙️
            </button>
          }
          items={menuItems}
        />
      </div>

      {/* Messages */}
      <MessageList
        messages={messages}
        isLoading={isLoading}
        isStreaming={isStreaming}
        onEditMessage={handleEditMessage}
        onRegenerateMessage={handleRegenerate}
      />

      {/* Input */}
      <MessageInput
        ref={messageInputRef}
        onSend={handleSendMessage}
        disabled={isLoading || isStreaming}
        showMentionButton={true}
        onMentionClick={() => setIsMentionModalOpen(true)}
      />

      {/* Mention Modal */}
      <MentionModal
        isOpen={isMentionModalOpen}
        onClose={() => setIsMentionModalOpen(false)}
        onSelect={handleMentionSelect}
      />

      {/* Edit Message Modal */}
      {editingMessage && (
        <EditMessageModal
          isOpen={editingMessageId !== null}
          onClose={handleCloseEdit}
          message={editingMessage}
          onSave={handleSaveEdit}
        />
      )}
    </div>
  );
}
