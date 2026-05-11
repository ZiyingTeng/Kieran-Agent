/**
 * CreateGroupModal Component
 */

import { useState } from 'react';
import { Modal } from '@/components/ui';
import * as api from '@/api';
import { useUserStore } from '@/stores/userStore';
import { useGroupStore } from '@/stores/groupStore';
import { useGirlfriendStore } from '@/stores/girlfriendStore';
import { Input, Button } from '@/components/ui';
import { clsx } from 'clsx';
import { toast } from '@/components/ui/Toast';

export function CreateGroupModal({
  isOpen,
  onClose,
}: {
  isOpen: boolean;
  onClose: () => void;
}) {
  const { currentUserId } = useUserStore();
  const { addGroup } = useGroupStore();
  const { girlfriends } = useGirlfriendStore();

  const [groupName, setGroupName] = useState('');
  const [background, setBackground] = useState('');
  const [selectedMembers, setSelectedMembers] = useState<Set<string>>(new Set());
  const [isLoading, setIsLoading] = useState(false);

  const handleToggleMember = (girlfriendId: string) => {
    const newSet = new Set(selectedMembers);
    if (newSet.has(girlfriendId)) {
      newSet.delete(girlfriendId);
    } else {
      newSet.add(girlfriendId);
    }
    setSelectedMembers(newSet);
  };

  const handleSubmit = async () => {
    if (!groupName.trim()) {
      toast.error('请输入群组名称');
      return;
    }

    if (selectedMembers.size < 2) {
      toast.error('请至少选择2个成员');
      return;
    }

    setIsLoading(true);

    try {
      const response = await api.createGroup({
        userId: currentUserId,
        name: groupName.trim(),
        members: Array.from(selectedMembers),
        ...(background.trim() && { background: background.trim() }),
      });

      if (response.success && response.group) {
        addGroup(response.group);
        toast.success('群组创建成功');
        handleClose();
      } else {
        toast.error(response.error || '创建失败');
      }
    } catch (error) {
      toast.error(`创建失败: ${(error as Error).message}`);
    } finally {
      setIsLoading(false);
    }
  };

  const handleClose = () => {
    setGroupName('');
    setBackground('');
    setSelectedMembers(new Set());
    onClose();
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={handleClose}
      title="创建群组"
      size="lg"
      footer={
        <>
          <Button variant="ghost" onClick={handleClose}>
            取消
          </Button>
          <Button onClick={handleSubmit} isLoading={isLoading}>
            创建 ({selectedMembers.size})
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <Input
          label="群组名称"
          value={groupName}
          onChange={(e) => setGroupName(e.target.value)}
          placeholder="例如: 周末聚会群"
        />

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            群聊背景 <span className="text-gray-400 font-normal">（可选）</span>
          </label>
          <textarea
            value={background}
            onChange={(e) => setBackground(e.target.value)}
            placeholder="描述聊天场景，例如：我们正在海边度假，坐在沙滩上..."
            rows={3}
            className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-pink-300 focus:border-transparent resize-none"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            选择成员 (至少2个)
          </label>
          <div className="max-h-[200px] overflow-y-auto border border-gray-200 rounded-lg p-2">
            {girlfriends.length === 0 ? (
              <p className="text-sm text-gray-500 text-center py-4">
                暂无可用角色，请先创建角色
              </p>
            ) : (
              girlfriends.map((gf) => (
                <button
                  key={gf.girlfriend_id}
                  onClick={() => handleToggleMember(gf.girlfriend_id)}
                  className={clsx(
                    'w-full flex items-center gap-3 px-3 py-2 rounded-lg text-left transition-colors',
                    selectedMembers.has(gf.girlfriend_id)
                      ? 'bg-pink-50 text-primary'
                      : 'hover:bg-gray-50'
                  )}
                >
                  <input
                    type="checkbox"
                    checked={selectedMembers.has(gf.girlfriend_id)}
                    onChange={() => {}}
                    className="rounded border-gray-300 text-primary focus:ring-primary"
                  />
                  <span className="text-sm font-medium">{gf.name}</span>
                </button>
              ))
            )}
          </div>
        </div>
      </div>
    </Modal>
  );
}
