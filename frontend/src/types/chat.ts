/**
 * Chat related types
 */

import type { MessageRoleValue } from '@/utils/constants';

// Message interface
export interface Message {
  msg_id: string;
  role: MessageRoleValue;
  content: string;
  timestamp?: string;
  girl_name?: string;
  girlfriend_name?: string;
  girlfriend_id?: string;
  is_editing?: boolean;
  emotion?: string;  // 情绪标签 (Happiness, Sadness, Anger, etc.)
  thoughts?: string; // 内心想法
}

// Chat session state for a girlfriend
export interface ChatSession {
  sessionId?: string;
  messages: Message[];
}

// SSE Event types
export interface SSEAIResponseEvent {
  name?: string;
  girlfriend_name?: string;
  response: string;
  emotion?: string;  // 情绪标签
  message: {
    timestamp: string;
  };
}

export interface SSECompleteEvent {
  success: boolean;
}

export interface SSEErrorEvent {
  error: string;
}

export type SSEEvent = SSEAIResponseEvent | SSECompleteEvent | SSEErrorEvent;

// Chat state per conversation (by girlfriend_id or group_id)
export interface ConversationState {
  sessionId?: string;
  messages: Message[];
  unreadCount?: number;
  isLoading?: boolean;  // 会话级别的加载状态
  isStreaming?: boolean;  // 会话级别的流式状态
}

// Chat Type
export const ChatType = {
  PRIVATE: 'private',
  GROUP: 'group',
} as const;

export type ChatTypeValue = typeof ChatType[keyof typeof ChatType];
