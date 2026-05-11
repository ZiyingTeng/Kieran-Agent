/**
 * GroupList Component
 */

import { useGroupStore } from '@/stores/groupStore';
import { GroupItem } from './GroupItem';
import { useChatStore } from '@/stores/chatStore';
import { ChatType } from '@/types/chat';
import * as api from '@/api';

export function GroupList() {
  const { groups, selectedGroupId, setSelectedGroup } = useGroupStore();
  const { setChatType, setCurrentChat, addMessage, clearMessages } = useChatStore();

  const handleSelectGroup = async (groupId: string) => {
    const group = groups.find((g) => g.group_id === groupId);
    if (!group) return;

    console.log('选择群组:', groupId, group.group_name);

    setSelectedGroup(groupId);
    setChatType(ChatType.GROUP);
    setCurrentChat(groupId, group.group_name);

    // 清空现有消息
    clearMessages(groupId);

    // 加载群组历史记录
    try {
      console.log('正在加载群组历史:', groupId);
      const response = await api.getGroupHistory(groupId);
      console.log('群组历史响应:', response);

      if (response.messages && response.messages.length > 0) {
        console.log('找到', response.messages.length, '条历史消息');
        // 将历史记录转换为 Message 格式并添加
        for (const msg of response.messages) {
          const message = {
            msg_id: msg.message_id || `history_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
            role: msg.role as 'user' | 'assistant',
            content: msg.content,
            timestamp: msg.timestamp || new Date().toISOString(),
            girl_name: msg.sender_name,
          };
          addMessage(groupId, message);
        }
        console.log('历史消息加载完成');
      } else {
        console.log('没有找到历史消息');
      }
    } catch (error) {
      console.error('加载群组历史记录失败:', error);
    }
  };

  if (groups.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center text-gray-400 text-sm px-4 text-center">
        暂无群组
        <br />
        点击下方按钮创建
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto">
      {groups.map((group) => (
        <GroupItem
          key={group.group_id}
          group={group}
          isActive={selectedGroupId === group.group_id}
          onClick={() => handleSelectGroup(group.group_id)}
        />
      ))}
    </div>
  );
}
