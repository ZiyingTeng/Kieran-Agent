/**
 * MessageBubble Component - Enhanced with beautiful styling
 */

import type { Message } from '@/types';
import { Avatar } from '@/components/ui';
import { format, isToday, isYesterday } from 'date-fns';
import { zhCN } from 'date-fns/locale';
import { clsx } from 'clsx';

export interface MessageBubbleProps {
  message: Message;
  isUser?: boolean;
  onEdit?: (messageId: string) => void;
  onRegenerate?: (messageId: string) => void;
}

export function MessageBubble({
  message,
  isUser = false,
  onEdit,
  onRegenerate,
}: MessageBubbleProps) {
  const formatTime = (timestamp?: string) => {
    if (!timestamp) return '';
    try {
      const date = new Date(timestamp);
      if (isToday(date)) {
        return format(date, 'HH:mm', { locale: zhCN });
      }
      if (isYesterday(date)) {
        return format(date, '昨天 HH:mm', { locale: zhCN });
      }
      return format(date, 'MM-dd HH:mm', { locale: zhCN });
    } catch {
      return '';
    }
  };

  const displayName = message.girl_name || message.girlfriend_name || 'AI';

  // 情绪标签对应的图标（支持中英文）
  const emotionIcons: Record<string, string> = {
    // 英文
    Happiness: '😊', Sadness: '😢', Anger: '😠', Fear: '😨',
    Surprise: '😲', Disgust: '🤢', Neutral: '😐', Shy: '😳', Guilty: '😔',
    // 中文
    开心: '😊', 高兴: '😊', 快乐: '😊', 喜悦: '😊', 幸福: '🥰',
    悲伤: '😢', 难过: '😢', 伤心: '😢',
    生气: '😠', 愤怒: '😠',
    恐惧: '😨', 害怕: '😨',
    惊讶: '😲', 震惊: '😲',
    厌恶: '🤢',
    平静: '😌', 淡然: '😌',
    害羞: '😳', 羞涩: '😳',
    内疚: '😔', 愧疚: '😔',
    爱意: '🥰', 心动: '💓', 甜蜜: '🥰',
    温柔: '🤗', 关心: '🤗', 体贴: '🤗',
    期待: '✨', 兴奋: '🤩', 激动: '🤩',
    焦虑: '😰', 紧张: '😰', 担心: '😟',
    无奈: '😮‍💨', 叹气: '😮‍💨',
    调皮: '😜', 俏皮: '😜', 撒娇: '🥺',
    委屈: '🥺', 心疼: '💔',
    思念: '🥹', 想念: '🥹',
    好奇: '🧐', 疑惑: '🤔',
    得意: '😏', 自信: '😎',
    感动: '🥹', 感恩: '🙏',
  };

  // 情绪标签对应的颜色（支持中英文）
  const emotionColors: Record<string, string> = {
    // 英文
    Happiness: 'bg-yellow-100 text-yellow-700 border-yellow-200',
    Sadness: 'bg-blue-100 text-blue-700 border-blue-200',
    Anger: 'bg-red-100 text-red-700 border-red-200',
    Fear: 'bg-purple-100 text-purple-700 border-purple-200',
    Surprise: 'bg-pink-100 text-pink-700 border-pink-200',
    Disgust: 'bg-green-100 text-green-700 border-green-200',
    Neutral: 'bg-gray-100 text-gray-700 border-gray-200',
    Shy: 'bg-rose-100 text-rose-700 border-rose-200',
    Guilty: 'bg-indigo-100 text-indigo-700 border-indigo-200',
    // 中文 - 暖色系（正面情绪）
    开心: 'bg-yellow-100 text-yellow-700 border-yellow-200',
    高兴: 'bg-yellow-100 text-yellow-700 border-yellow-200',
    快乐: 'bg-yellow-100 text-yellow-700 border-yellow-200',
    喜悦: 'bg-yellow-100 text-yellow-700 border-yellow-200',
    幸福: 'bg-pink-100 text-pink-700 border-pink-200',
    爱意: 'bg-pink-100 text-pink-700 border-pink-200',
    心动: 'bg-pink-100 text-pink-700 border-pink-200',
    甜蜜: 'bg-pink-100 text-pink-700 border-pink-200',
    温柔: 'bg-rose-50 text-rose-600 border-rose-200',
    关心: 'bg-rose-50 text-rose-600 border-rose-200',
    体贴: 'bg-rose-50 text-rose-600 border-rose-200',
    期待: 'bg-amber-100 text-amber-700 border-amber-200',
    兴奋: 'bg-orange-100 text-orange-700 border-orange-200',
    激动: 'bg-orange-100 text-orange-700 border-orange-200',
    感动: 'bg-pink-100 text-pink-700 border-pink-200',
    感恩: 'bg-pink-100 text-pink-700 border-pink-200',
    得意: 'bg-amber-100 text-amber-700 border-amber-200',
    自信: 'bg-amber-100 text-amber-700 border-amber-200',
    // 中文 - 冷色系（负面/中性情绪）
    悲伤: 'bg-blue-100 text-blue-700 border-blue-200',
    难过: 'bg-blue-100 text-blue-700 border-blue-200',
    伤心: 'bg-blue-100 text-blue-700 border-blue-200',
    生气: 'bg-red-100 text-red-700 border-red-200',
    愤怒: 'bg-red-100 text-red-700 border-red-200',
    恐惧: 'bg-purple-100 text-purple-700 border-purple-200',
    害怕: 'bg-purple-100 text-purple-700 border-purple-200',
    惊讶: 'bg-pink-100 text-pink-700 border-pink-200',
    震惊: 'bg-pink-100 text-pink-700 border-pink-200',
    厌恶: 'bg-green-100 text-green-700 border-green-200',
    平静: 'bg-gray-100 text-gray-600 border-gray-200',
    淡然: 'bg-gray-100 text-gray-600 border-gray-200',
    害羞: 'bg-rose-100 text-rose-700 border-rose-200',
    羞涩: 'bg-rose-100 text-rose-700 border-rose-200',
    内疚: 'bg-indigo-100 text-indigo-700 border-indigo-200',
    愧疚: 'bg-indigo-100 text-indigo-700 border-indigo-200',
    焦虑: 'bg-amber-100 text-amber-700 border-amber-200',
    紧张: 'bg-amber-100 text-amber-700 border-amber-200',
    担心: 'bg-amber-100 text-amber-700 border-amber-200',
    无奈: 'bg-slate-100 text-slate-600 border-slate-200',
    叹气: 'bg-slate-100 text-slate-600 border-slate-200',
    调皮: 'bg-cyan-100 text-cyan-700 border-cyan-200',
    俏皮: 'bg-cyan-100 text-cyan-700 border-cyan-200',
    撒娇: 'bg-pink-100 text-pink-600 border-pink-200',
    委屈: 'bg-violet-100 text-violet-700 border-violet-200',
    心疼: 'bg-violet-100 text-violet-700 border-violet-200',
    思念: 'bg-sky-100 text-sky-700 border-sky-200',
    想念: 'bg-sky-100 text-sky-700 border-sky-200',
    好奇: 'bg-teal-100 text-teal-700 border-teal-200',
    疑惑: 'bg-teal-100 text-teal-700 border-teal-200',
  };

  return (
    <div
      className={clsx(
        'flex gap-3 mb-5 animate-fade-in group',
        isUser && 'flex-row-reverse'
      )}
    >
      {/* Avatar */}
      <div className="flex-shrink-0">
        <Avatar
          name={isUser ? '用户' : displayName}
          size="lg"
          variant={isUser ? 'primary' : 'system'}
          className="shadow-md"
        />
      </div>

      {/* Message Content */}
      <div
        className={clsx(
          'flex flex-col max-w-[65%]',
          isUser ? 'items-end' : 'items-start'
        )}
      >
        {/* Name for assistant */}
        {!isUser && (
          <span className="text-sm font-semibold text-gray-700 mb-1.5 ml-1 flex items-center gap-1.5">
            <span>💝</span>
            <span>{displayName}</span>
            {/* 情绪标签 */}
            {message.emotion && (
              <span className={`ml-2 px-2 py-0.5 rounded-full text-xs border ${emotionColors[message.emotion] || 'bg-gray-100 text-gray-600 border-gray-200'} flex items-center gap-1`}>
                <span>{emotionIcons[message.emotion] || '💭'}</span>
                <span>{message.emotion}</span>
              </span>
            )}
          </span>
        )}

        {/* Bubble */}
        <div
          className={clsx(
            'px-5 py-3.5 rounded-2xl text-[15px] leading-relaxed break-words whitespace-pre-wrap shadow-md',
            'transition-all duration-200',
            isUser
              ? 'bg-gradient-to-br from-[#ff6b9d] to-[#c44569] text-white rounded-br-sm shadow-pink-200'
              : 'bg-white text-gray-800 rounded-bl-sm shadow-gray-200/50 border border-gray-100'
          )}
        >
          {message.content}
        </div>

        {/* Time */}
        <span
          className={clsx(
            'text-xs text-gray-400 mt-1.5 flex items-center gap-1',
            isUser ? 'mr-1' : 'ml-1'
          )}
        >
          <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          {formatTime(message.timestamp)}
        </span>

        {/* Action buttons for assistant messages */}
        {!isUser && (onEdit || onRegenerate) && (
          <div className="flex gap-2 mt-2 ml-1 opacity-0 group-hover:opacity-100 transition-opacity">
            {onEdit && (
              <button
                onClick={() => onEdit(message.msg_id)}
                className="px-3 py-1.5 text-xs bg-gradient-to-r from-amber-50 to-orange-50 text-amber-700 rounded-full hover:from-amber-100 hover:to-orange-100 transition-all shadow-sm border border-amber-200 flex items-center gap-1"
                title="编辑消息"
              >
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                </svg>
                编辑
              </button>
            )}
            {onRegenerate && (
              <button
                onClick={() => onRegenerate(message.msg_id)}
                className="px-3 py-1.5 text-xs bg-gradient-to-r from-blue-50 to-indigo-50 text-blue-700 rounded-full hover:from-blue-100 hover:to-indigo-100 transition-all shadow-sm border border-blue-200 flex items-center gap-1"
                title="重新生成"
              >
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                </svg>
                重试
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
