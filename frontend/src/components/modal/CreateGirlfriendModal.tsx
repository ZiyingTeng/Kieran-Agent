/**
 * CreateGirlfriendModal Component
 */

import { useState } from 'react';
import { Modal } from '@/components/ui';
import * as api from '@/api';
import { useGirlfriendStore } from '@/stores/girlfriendStore';
import { useUserStore } from '@/stores/userStore';
import { Input, Textarea, Button } from '@/components/ui';
import { toast } from '@/components/ui/Toast';

export function CreateGirlfriendModal({
  isOpen,
  onClose,
}: {
  isOpen: boolean;
  onClose: () => void;
}) {
  const { addGirlfriend } = useGirlfriendStore();
  const { currentUserId } = useUserStore();

  const [name, setName] = useState('');
  const [systemPrompt, setSystemPrompt] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async () => {
    if (!name.trim()) {
      toast.error('请输入角色名称');
      return;
    }

    if (!systemPrompt.trim()) {
      toast.error('请输入系统提示词');
      return;
    }

    setIsLoading(true);

    try {
      const newGirlfriend = await api.createGirlfriend({
        name: name.trim(),
        sys_prompt: systemPrompt.trim(),
        userId: currentUserId,
      });

      addGirlfriend(newGirlfriend);
      toast.success('角色创建成功');
      handleClose();
    } catch (error) {
      toast.error(`创建失败: ${(error as Error).message}`);
    } finally {
      setIsLoading(false);
    }
  };

  const handleClose = () => {
    setName('');
    setSystemPrompt('');
    onClose();
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={handleClose}
      title="创建自定义角色"
      size="md"
      footer={
        <>
          <Button variant="ghost" onClick={handleClose}>
            取消
          </Button>
          <Button onClick={handleSubmit} isLoading={isLoading}>
            创建
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
          placeholder="设置角色的行为和说话方式..."
          rows={6}
          required
        />
      </div>
    </Modal>
  );
}
