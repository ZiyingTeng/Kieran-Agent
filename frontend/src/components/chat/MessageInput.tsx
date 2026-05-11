/**
 * MessageInput Component - Enhanced with mention insertion
 */

import { useState, useRef, useImperativeHandle, forwardRef } from 'react';
import type { KeyboardEvent } from 'react';
import { Button } from '@/components/ui';
import { clsx } from 'clsx';

export interface MessageInputProps {
  onSend: (message: string) => void;
  disabled?: boolean;
  placeholder?: string;
  showMentionButton?: boolean;
  onMentionClick?: () => void;
}

export interface MessageInputRef {
  insertMention: (name: string) => void;
  focus: () => void;
}

export const MessageInput = forwardRef<MessageInputRef, MessageInputProps>(
  function MessageInput({
    onSend,
    disabled = false,
    placeholder = '输入消息...',
    showMentionButton = false,
    onMentionClick,
  }: MessageInputProps, ref) {
  const [message, setMessage] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // 暴露方法给父组件
  useImperativeHandle(ref, () => ({
    insertMention: (name: string) => {
      const textarea = textareaRef.current;
      if (!textarea) return;

      const start = textarea.selectionStart;
      const end = textarea.selectionEnd;
      const before = message.substring(0, start);
      const after = message.substring(end);

      // 在光标位置插入 @角色名
      const newMessage = `${before}@${name}${after}`;
      setMessage(newMessage);

      // 设置光标位置到插入文本后面
      setTimeout(() => {
        const newPosition = start + name.length + 1;
        textarea.setSelectionRange(newPosition, newPosition);
        textarea.focus();
      }, 0);
    },
    focus: () => {
      textareaRef.current?.focus();
    },
  }));

  const handleSend = () => {
    const trimmed = message.trim();
    if (trimmed && !disabled) {
      onSend(trimmed);
      setMessage('');
      // Reset textarea height
      if (textareaRef.current) {
        textareaRef.current.style.height = 'auto';
      }
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleInput = () => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 120)}px`;
    }
  };

  return (
    <div className="px-5 py-4 bg-gradient-to-t from-gray-50 to-white border-t border-gray-200">
      <div className="flex items-end gap-3">
        {/* Mention Button */}
        {showMentionButton && onMentionClick && (
          <button
            onClick={onMentionClick}
            className="px-4 py-3 rounded-xl font-semibold text-white transition-all duration-200 flex-shrink-0 shadow-md bg-gradient-to-r from-indigo-500 to-purple-500 hover:from-indigo-600 hover:to-purple-600 hover:shadow-lg active:scale-95"
            title="@角色"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
            </svg>
          </button>
        )}

        {/* Input */}
        <div className="flex-1 relative">
          <textarea
            ref={textareaRef}
            value={message}
            onChange={(e) => {
              setMessage(e.target.value);
              handleInput();
            }}
            onKeyDown={handleKeyDown}
            placeholder={placeholder}
            disabled={disabled}
            rows={1}
            className={clsx(
              'w-full px-4 py-3 rounded-2xl border border-gray-300 resize-none bg-white shadow-sm',
              'focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary focus:shadow-md',
              'transition-all duration-200',
              'disabled:opacity-50 disabled:cursor-not-allowed disabled:bg-gray-100',
              'max-h-[120px] placeholder:text-gray-400'
            )}
            style={{ minHeight: '48px' }}
          />
        </div>

        {/* Send Button */}
        <Button
          onClick={handleSend}
          disabled={!message.trim() || disabled}
          className="flex-shrink-0 px-6 py-3 rounded-full bg-gradient-to-r from-[#ff6b9d] to-[#c44569] text-white font-medium shadow-lg hover:shadow-xl hover:scale-105 active:scale-95 disabled:opacity-40 disabled:hover:scale-100"
        >
          {disabled ? (
            <span className="flex items-center gap-2">
              <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              发送中
            </span>
          ) : (
            <span className="flex items-center gap-2">
              发送
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
              </svg>
            </span>
          )}
        </Button>
      </div>
    </div>
  );
});
