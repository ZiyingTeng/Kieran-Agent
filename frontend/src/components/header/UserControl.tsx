/**
 * UserControl Component
 */

import { useState } from 'react';
import type { KeyboardEvent } from 'react';
import { useUserStore } from '@/stores/userStore';
import { useChatStore } from '@/stores/chatStore';
import { Input, Button } from '@/components/ui';

export function UserControl() {
  const { currentUserId, setUserId } = useUserStore();
  const { setCurrentUser } = useChatStore();
  const [isEditing, setIsEditing] = useState(false);
  const [tempUserId, setTempUserId] = useState(currentUserId);

  const handleSwitch = () => {
    if (tempUserId.trim()) {
      const newUserId = tempUserId.trim();
      setUserId(newUserId);
      // Notify chatStore about user change to clear conversations
      setCurrentUser(newUserId);
      setIsEditing(false);
    }
  };

  const handleKeyDown = (e: KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleSwitch();
    } else if (e.key === 'Escape') {
      setTempUserId(currentUserId);
      setIsEditing(false);
    }
  };

  if (isEditing) {
    return (
      <div className="flex items-center gap-2">
        <Input
          value={tempUserId}
          onChange={(e) => setTempUserId(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="输入用户ID"
          className="w-40"
        />
        <Button size="sm" onClick={handleSwitch} variant="primary">
          确定
        </Button>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2">
      <span className="text-sm opacity-90 font-medium text-white">用户: {currentUserId}</span>
      <Button
        size="sm"
        variant="transparent"
        onClick={() => setIsEditing(true)}
      >
        切换
      </Button>
    </div>
  );
}
