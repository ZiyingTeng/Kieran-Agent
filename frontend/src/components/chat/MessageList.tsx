/**
 * MessageList Component
 */

import { useEffect, useRef } from 'react';
import type { Message } from '@/types';
import { MessageBubble } from './MessageBubble';
import { MessageRole } from '@/utils/constants';
import { Avatar } from '@/components/ui';
import { clsx } from 'clsx';

export interface MessageListProps {
  messages: Message[];
  isLoading?: boolean;
  isStreaming?: boolean;
  onEditMessage?: (messageId: string) => void;
  onRegenerateMessage?: (messageId: string) => void;
}

export function MessageList({
  messages,
  isLoading = false,
  isStreaming = false,
  onEditMessage,
  onRegenerateMessage,
}: MessageListProps) {
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = (smooth = true) => {
    messagesEndRef.current?.scrollIntoView({
      behavior: smooth ? 'smooth' : 'instant',
    });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isStreaming]);

  if (messages.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center text-gray-400">
          <div className="text-6xl mb-4">💬</div>
          <h2 className="text-xl font-semibold mb-2">欢迎来到AI女友聊天系统</h2>
          <p>选择一个女友或群组开始聊天吧～</p>
        </div>
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className="flex-1 overflow-y-auto px-5 py-4"
    >
      {messages.map((message) => (
        <div
          key={message.msg_id}
          className={clsx(
            'group',
            message.role === MessageRole.ASSISTANT && 'hover:opacity-100'
          )}
        >
          <MessageBubble
            message={message}
            isUser={message.role === MessageRole.USER}
            onEdit={
              message.role === MessageRole.ASSISTANT
                ? onEditMessage
                : undefined
            }
            onRegenerate={
              message.role === MessageRole.ASSISTANT
                ? onRegenerateMessage
                : undefined
            }
          />
        </div>
      ))}

      {/* Loading indicator */}
      {isLoading && (
        <div className="flex gap-3 mb-5">
          <Avatar name="AI" size="md" variant="system" />
          <div className="bg-white px-4 py-3 rounded-2xl rounded-bl-sm shadow-sm">
            <div className="flex gap-1">
              <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
              <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
              <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
            </div>
          </div>
        </div>
      )}

      <div ref={messagesEndRef} />
    </div>
  );
}
