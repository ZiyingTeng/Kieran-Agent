/**
 * EditMessageModal Component
 */

import { useState, useEffect } from 'react';
import type { KeyboardEvent } from 'react';
import { Modal } from '@/components/ui';
import { Textarea, Button } from '@/components/ui';
import type { Message } from '@/types';
import { toast } from '@/components/ui/Toast';

export function EditMessageModal({
  isOpen,
  onClose,
  message,
  onSave,
}: {
  isOpen: boolean;
  onClose: () => void;
  message: Message | null;
  onSave: (messageId: string, newContent: string) => void;
}) {
  const [content, setContent] = useState('');

  useEffect(() => {
    if (message) {
      setContent(message.content);
    }
  }, [message]);

  const handleSave = () => {
    if (!message || !content.trim()) {
      toast.error('消息内容不能为空');
      return;
    }

    onSave(message.msg_id, content.trim());
    handleClose();
  };

  const handleClose = () => {
    setContent('');
    onClose();
  };

  const handleKeyDown = (e: KeyboardEvent) => {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
      handleSave();
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={handleClose}
      title="编辑消息"
      size="md"
      footer={
        <>
          <Button variant="danger" onClick={handleClose}>
            取消
          </Button>
          <Button onClick={handleSave}>保存</Button>
        </>
      }
    >
      <Textarea
        value={content}
        onChange={(e) => setContent(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="编辑消息内容..."
        rows={6}
        className="border-green-300 focus:ring-green-500"
      />
      <p className="text-xs text-gray-500 mt-2">
        提示: 按 Ctrl+Enter 或 Cmd+Enter 快速保存
      </p>
    </Modal>
  );
}
