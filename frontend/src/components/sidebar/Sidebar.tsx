/**
 * Sidebar Component - Enhanced with larger tabs
 */

import { useState } from 'react';
import { Tabs } from '@/components/ui';
import type { Tab } from '@/components/ui';
import { GirlfriendList } from './GirlfriendList';
import { GroupList } from './GroupList';
import { CreateGirlfriendModal } from '@/components/modal/CreateGirlfriendModal';
import { CreateGroupModal } from '@/components/modal/CreateGroupModal';

export function Sidebar() {
  const [activeTab, setActiveTab] = useState<'girlfriends' | 'groups'>('girlfriends');
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);

  const tabs: Tab[] = [
    {
      id: 'girlfriends',
      label: '💕 角色列表',
    },
    {
      id: 'groups',
      label: '👥 群聊列表',
    },
  ];

  const handleCreate = () => {
    setIsCreateModalOpen(true);
  };

  return (
    <div className="w-[300px] bg-white border-r border-gray-200 flex flex-col shadow-lg">
      {/* Header with larger tabs */}
      <div className="p-4 border-b border-gray-100 bg-gradient-to-b from-pink-50/50 to-white">
        <Tabs
          tabs={tabs}
          activeTab={activeTab}
          onChange={(tabId) => setActiveTab(tabId as any)}
        />
      </div>

      {/* Content */}
      {activeTab === 'girlfriends' ? (
        <GirlfriendList />
      ) : (
        <GroupList />
      )}

      {/* Create button */}
      <div className="p-4 border-t border-gray-100 bg-gray-50/50">
        <button
          onClick={handleCreate}
          className="w-full py-3.5 rounded-xl font-bold text-white text-base transition-all duration-200 hover:shadow-lg hover:scale-[1.02] active:scale-[0.98] flex items-center justify-center gap-2"
          style={{
            background:
              activeTab === 'girlfriends'
                ? 'linear-gradient(135deg, #ff6b9d 0%, #c44569 100%)'
                : 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
          }}
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M12 4v16m8-8H4" />
          </svg>
          {activeTab === 'girlfriends' ? '创建新角色' : '创建新群组'}
        </button>
      </div>

      {/* Modals */}
      {isCreateModalOpen && activeTab === 'girlfriends' && (
        <CreateGirlfriendModal
          isOpen={isCreateModalOpen}
          onClose={() => setIsCreateModalOpen(false)}
        />
      )}
      {isCreateModalOpen && activeTab === 'groups' && (
        <CreateGroupModal
          isOpen={isCreateModalOpen}
          onClose={() => setIsCreateModalOpen(false)}
        />
      )}
    </div>
  );
}
