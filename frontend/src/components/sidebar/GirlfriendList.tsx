/**
 * GirlfriendList Component
 */

import { useState } from 'react';
import { useGirlfriendStore } from '@/stores/girlfriendStore';
import { GirlfriendItem } from './GirlfriendItem';
import { EditGirlfriendModal } from '@/components/modal/EditGirlfriendModal';
import { useChatStore } from '@/stores/chatStore';
import { useUserStore } from '@/stores/userStore';
import { ChatType } from '@/types/chat';
import { toast } from '@/components/ui/Toast';
import type { Girlfriend } from '@/types';
import * as api from '@/api';

export function GirlfriendList() {
  const { girlfriends, selectedGirlfriendId, setSelectedGirlfriend, removeGirlfriend } =
    useGirlfriendStore();
  const { setChatType, setCurrentChat, addMessage } = useChatStore();
  const { currentUserId } = useUserStore();

  const [editingGirlfriend, setEditingGirlfriend] = useState<Girlfriend | null>(null);

  const handleSelectGirlfriend = async (girlfriendId: string, name: string) => {
    setSelectedGirlfriend(girlfriendId);
    setChatType(ChatType.PRIVATE);
    setCurrentChat(girlfriendId, name);

    // 加载历史记录
    try {
      const response = await api.getHistory(currentUserId, girlfriendId);
      if (response.success && response.history) {
        // 清空现有消息
        const chatId = girlfriendId;

        // 将历史记录转换为 Message 格式并添加
        for (const msg of response.history) {
          const message = {
            msg_id: `history_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
            role: msg.role as 'user' | 'assistant',
            content: msg.content,
            timestamp: new Date().toISOString(),
            girl_name: msg.name || name,
          };
          addMessage(chatId, message);
        }
      }
    } catch (error) {
      console.error('加载历史记录失败:', error);
    }
  };

  const handleDelete = async (girlfriend: Girlfriend) => {
    if (!confirm(`确定要删除角色「${girlfriend.name}」吗？此操作不可恢复。`)) {
      return;
    }
    try {
      await api.deleteGirlfriend(girlfriend.expertId, currentUserId);
      removeGirlfriend(girlfriend.girlfriend_id);
      toast.success('角色已删除');
    } catch (error) {
      toast.error(`删除失败: ${(error as Error).message}`);
    }
  };

  if (girlfriends.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center text-gray-400 text-sm px-4 text-center">
        暂无角色
      </div>
    );
  }

  return (
    <>
      <div className="flex-1 overflow-y-auto">
        {girlfriends.map((girlfriend) => (
          <GirlfriendItem
            key={girlfriend.girlfriend_id}
            girlfriend={girlfriend}
            isActive={selectedGirlfriendId === girlfriend.girlfriend_id}
            onClick={() => handleSelectGirlfriend(girlfriend.girlfriend_id, girlfriend.name)}
            onEdit={() => setEditingGirlfriend(girlfriend)}
            onDelete={() => handleDelete(girlfriend)}
          />
        ))}
      </div>
      {editingGirlfriend && (
        <EditGirlfriendModal
          isOpen={!!editingGirlfriend}
          onClose={() => setEditingGirlfriend(null)}
          girlfriend={editingGirlfriend}
        />
      )}
    </>
  );
}
