/**
 * MentionModal Component - For selecting characters to @ in group chat
 * Click on a character to immediately insert @name and close
 */

import { Modal } from '@/components/ui';
import { useGirlfriendStore } from '@/stores/girlfriendStore';
import { useGroupStore } from '@/stores/groupStore';
import { useChatStore } from '@/stores/chatStore';
import { Avatar } from '@/components/ui';

export interface MentionModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSelect: (name: string) => void;
}

export function MentionModal({
  isOpen,
  onClose,
  onSelect,
}: MentionModalProps) {
  const { girlfriends } = useGirlfriendStore();
  const { currentChatId, chatType } = useChatStore();

  // 获取当前群组的成员
  const getCurrentGroupMembers = () => {
    if (chatType !== 'group' || !currentChatId) return [];

    // 从群组列表中找到当前群组
    const { groups } = useGroupStore.getState();
    const currentGroup = groups.find(g => g.group_id === currentChatId);
    return currentGroup?.members || [];
  };

  const groupMemberIds = getCurrentGroupMembers();
  const availableGirlfriends = girlfriends.filter(gf =>
    groupMemberIds.includes(gf.girlfriend_id)
  );

  const handleSelect = (name: string) => {
    onSelect(name);
    onClose();
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="💬 选择要@的角色"
      size="md"
      footer={
        <button
          onClick={onClose}
          className="px-4 py-2 text-gray-600 hover:text-gray-800 hover:bg-gray-100 rounded-lg transition-colors"
        >
          取消
        </button>
      }
    >
      {availableGirlfriends.length === 0 ? (
        <div className="text-center py-12">
          <div className="text-6xl mb-4">👥</div>
          <p className="text-gray-500">该群组暂无成员</p>
          <p className="text-sm text-gray-400 mt-2">请先添加角色到群组</p>
        </div>
      ) : (
        <div className="space-y-2 max-h-[350px] overflow-y-auto pr-2">
          <p className="text-sm text-gray-500 mb-3">点击角色即可在光标位置插入 @角色名</p>
          {availableGirlfriends.map((gf) => (
            <button
              key={gf.girlfriend_id}
              onClick={() => handleSelect(gf.name)}
              className="w-full flex items-center gap-3 px-4 py-3.5 rounded-xl text-left transition-all duration-200 border-2 hover:bg-pink-50 hover:border-pink-300 border-transparent shadow-sm hover:shadow-md"
            >
              <Avatar
                name={gf.name}
                size="lg"
                variant={gf.is_system ? 'system' : 'custom'}
              />
              <div className="flex-1 min-w-0">
                <p className="font-medium text-gray-900 truncate">
                  @{gf.name}
                </p>
                {gf.description && (
                  <p className="text-sm text-gray-500 truncate">
                    {gf.description}
                  </p>
                )}
              </div>
              <span className="text-gray-400">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                </svg>
              </span>
            </button>
          ))}
        </div>
      )}
    </Modal>
  );
}
