/**
 * EditGirlfriendModal Component
 */

import { useState, useEffect } from 'react';
import { Modal } from '@/components/ui';
import * as api from '@/api';
import { useGirlfriendStore } from '@/stores/girlfriendStore';
import { useUserStore } from '@/stores/userStore';
import { Input, Textarea, Button } from '@/components/ui';
import { toast } from '@/components/ui/Toast';
import type { Girlfriend } from '@/types';

export function EditGirlfriendModal({
  isOpen,
  onClose,
  girlfriend,
}: {
  isOpen: boolean;
  onClose: () => void;
  girlfriend: Girlfriend;
}) {
  const { updateGirlfriend } = useGirlfriendStore();
  const { currentUserId } = useUserStore();

  const [name, setName] = useState(girlfriend.name);
  const [systemPrompt, setSystemPrompt] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isLoadingDetail, setIsLoadingDetail] = useState(true);

  useEffect(() => {
    if (isOpen) {
      setName(girlfriend.name);
      // Load full detail to get sys_prompt
      api.getGirlfriend(girlfriend.expertId)
        .then((detail) => {
          setSystemPrompt(detail.sys_prompt || detail.description || '');
        })
        .catch(() => {
          setSystemPrompt(girlfriend.description || '');
        })
        .finally(() => setIsLoadingDetail(false));
    }
  }, [isOpen, girlfriend.expertId, girlfriend.name, girlfriend.description]);

  const handleSubmit = async () => {
    if (!name.trim()) {
      toast.error('请输入角色名称');
      return;
    }

    setIsLoading(true);

    try {
      const updated = await api.updateGirlfriend(
        girlfriend.expertId,
        {
          name: name.trim(),
          sys_prompt: systemPrompt.trim() || undefined,
        },
        currentUserId
      );

      updateGirlfriend(girlfriend.girlfriend_id, {
        name: updated.name,
        description: updated.description,
      });
      toast.success('角色更新成功');
      onClose();
    } catch (error) {
      toast.error(`更新失败: ${(error as Error).message}`);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="编辑角色"
      size="md"
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            取消
          </Button>
          <Button onClick={handleSubmit} isLoading={isLoading} disabled={isLoadingDetail}>
            保存
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <Input
          label="角色名称"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="例如: 小美"
        />
        <Textarea
          label="系统提示词"
          value={systemPrompt}
          onChange={(e) => setSystemPrompt(e.target.value)}
          placeholder={isLoadingDetail ? '加载中...' : '设置角色的行为和说话方式...'}
          rows={6}
          disabled={isLoadingDetail}
        />
      </div>
    </Modal>
  );
}
