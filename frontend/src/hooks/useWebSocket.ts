/**
 * useWebSocket - WebSocket 连接管理 Hook
 * 支持实时聊天和心跳问候推送
 */

import { useRef, useCallback, useEffect } from 'react';
import { useUserStore } from '@/stores/userStore';
import { useGirlfriendStore } from '@/stores/girlfriendStore';
import { useChatStore } from '@/stores/chatStore';
import type { Message } from '@/types';
import { MessageRole } from '@/utils/constants';

interface WebSocketMessage {
  type: 'chat_response' | 'heartbeat_greeting' | 'heartbeat_ack' | 'pong' | 'error';
  content?: string;
  expert_id?: string;
  timestamp?: string;
  message?: string;
  emotion?: string;
}

interface UseWebSocketReturn {
  isConnected: boolean;
  connect: (userId: string, expertId: string) => void;
  disconnect: () => void;
  sendMessage: (content: string) => void;
}

let globalWs: WebSocket | null = null;
let heartbeatInterval: number | null = null;
let reconnectTimeout: number | null = null;

export function useWebSocket(): UseWebSocketReturn {
  const { currentUserId } = useUserStore();
  const { getSelectedGirlfriend } = useGirlfriendStore();
  const { currentChatId, addMessage, setIsLoading } = useChatStore();

  const isConnectedRef = useRef(false);
  const currentUserIdRef = useRef<string | null>(currentUserId);
  const currentExpertIdRef = useRef<string | null>(null);

  // 更新 refs
  useEffect(() => {
    currentUserIdRef.current = currentUserId;
  }, [currentUserId]);

  const generateMessageId = () => `msg_ws_${Date.now()}_${Math.random().toString(36).substring(2, 11)}`;

  const connect = useCallback((userId: string, expertId: string) => {
    // 如果已经连接到同一个用户和角色，不重新连接
    if (globalWs && globalWs.readyState === WebSocket.OPEN &&
        currentUserIdRef.current === userId && currentExpertIdRef.current === expertId) {
      return;
    }

    // 关闭现有连接
    if (globalWs) {
      globalWs.close();
    }
    if (heartbeatInterval) {
      clearInterval(heartbeatInterval);
    }
    if (reconnectTimeout) {
      clearTimeout(reconnectTimeout);
    }

    const wsUrl = `ws://localhost:8001/ws/${userId}/${expertId}`;
    console.log(`[WebSocket] 连接到: ${wsUrl}`);

    try {
      globalWs = new WebSocket(wsUrl);

      globalWs.onopen = () => {
        console.log('[WebSocket] ✅ 连接成功');
        isConnectedRef.current = true;
        currentUserIdRef.current = userId;
        currentExpertIdRef.current = expertId;

        // 启动心跳（每 30 秒）
        heartbeatInterval = window.setInterval(() => {
          if (globalWs && globalWs.readyState === WebSocket.OPEN) {
            globalWs.send(JSON.stringify({ type: 'heartbeat' }));
          }
        }, 30000);

        // 通知连接状态变化
        window.dispatchEvent(new CustomEvent('websocket:connected'));
      };

      globalWs.onmessage = (event) => {
        try {
          const data: WebSocketMessage = JSON.parse(event.data);

          switch (data.type) {
            case 'chat_response':
              // 聊天响应 - 清除加载状态
              if (data.content && currentChatId) {
                setIsLoading(currentChatId, false);
                const girlfriend = getSelectedGirlfriend();
                const assistantMsg: Message = {
                  msg_id: generateMessageId(),
                  role: MessageRole.ASSISTANT,
                  content: data.content,
                  timestamp: data.timestamp || new Date().toISOString(),
                  girl_name: girlfriend?.name,
                  emotion: data.emotion,
                };
                addMessage(currentChatId, assistantMsg);
              }
              break;

            case 'heartbeat_greeting':
              // 心跳问候（主动推送！）
              console.log('[WebSocket] 💓 收到心跳问候:', data.content);
              if (data.content && currentChatId) {
                const girlfriend = getSelectedGirlfriend();
                const greetingMsg: Message = {
                  msg_id: generateMessageId(),
                  role: MessageRole.ASSISTANT,
                  content: `💓 ${data.content}`,
                  timestamp: data.timestamp || new Date().toISOString(),
                  girl_name: girlfriend?.name,
                };
                addMessage(currentChatId, greetingMsg);

                // 显示浏览器通知
                showNotification('新消息', data.content);
              }
              break;

            case 'heartbeat_ack':
              // 心跳确认
              console.log('[WebSocket] 💓 心跳确认');
              break;

            case 'pong':
              // Pong 响应
              break;

            case 'error':
              console.error('[WebSocket] 错误:', data.message);
              break;
          }
        } catch (error) {
          console.error('[WebSocket] 解析消息失败:', error);
        }
      };

      globalWs.onclose = (event) => {
        console.log('[WebSocket] ❌ 连接关闭:', event.code, event.reason);
        isConnectedRef.current = false;

        if (heartbeatInterval) {
          clearInterval(heartbeatInterval);
          heartbeatInterval = null;
        }

        // 通知连接状态变化
        window.dispatchEvent(new CustomEvent('websocket:disconnected'));

        // 5 秒后尝试重连
        if (currentUserIdRef.current && currentExpertIdRef.current) {
          reconnectTimeout = window.setTimeout(() => {
            console.log('[WebSocket] 🔄 尝试重连...');
            connect(currentUserIdRef.current!, currentExpertIdRef.current!);
          }, 5000);
        }
      };

      globalWs.onerror = (error) => {
        console.error('[WebSocket] 错误:', error);
      };

    } catch (error) {
      console.error('[WebSocket] 连接失败:', error);
    }
  }, [currentChatId, getSelectedGirlfriend, addMessage]);

  const disconnect = useCallback(() => {
    if (globalWs) {
      globalWs.close();
      globalWs = null;
    }
    if (heartbeatInterval) {
      clearInterval(heartbeatInterval);
      heartbeatInterval = null;
    }
    if (reconnectTimeout) {
      clearTimeout(reconnectTimeout);
      reconnectTimeout = null;
    }
    isConnectedRef.current = false;
    currentUserIdRef.current = null;
    currentExpertIdRef.current = null;
  }, []);

  const sendMessage = useCallback((content: string) => {
    if (globalWs && globalWs.readyState === WebSocket.OPEN) {
      const message = {
        type: 'chat',
        content: content,
      };
      globalWs.send(JSON.stringify(message));
      console.log('[WebSocket] 发送消息:', content);
    } else {
      console.warn('[WebSocket] 未连接，无法发送消息');
    }
  }, []);

  return {
    isConnected: isConnectedRef.current,
    connect,
    disconnect,
    sendMessage,
  };
}

// 显示浏览器通知
function showNotification(title: string, body: string) {
  if ('Notification' in window) {
    if (Notification.permission === 'granted') {
      new Notification(title, {
        body,
        icon: '/favicon.ico',
      });
    } else if (Notification.permission !== 'denied') {
      Notification.requestPermission().then((permission) => {
        if (permission === 'granted') {
          new Notification(title, { body });
        }
      });
    }
  }
}
