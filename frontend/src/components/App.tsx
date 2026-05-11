/**
 * App Component - Main application
 */

import { useEffect, useState } from 'react';
import { TopBar } from '@/components/header/TopBar';
import { Sidebar } from '@/components/sidebar/Sidebar';
import { ChatArea } from '@/components/chat/ChatArea';
import { useUserStore } from '@/stores/userStore';
import { useGirlfriendStore } from '@/stores/girlfriendStore';
import { useGroupStore } from '@/stores/groupStore';
import * as api from '@/api';
import { useChatStore } from '@/stores/chatStore';

function App() {
  const { currentUserId } = useUserStore();
  const { setGirlfriends } = useGirlfriendStore();
  const { setGroups } = useGroupStore();
  const { setCurrentUser } = useChatStore();
  const [isLoading, setIsLoading] = useState(true);

  // Load initial data
  useEffect(() => {
    const loadInitialData = async () => {
      try {
        // Notify chatStore about user change to clear previous user's conversations
        setCurrentUser(currentUserId);

        // Load girlfriends - 后端直接返回数组
        const girlfriends = await api.getGirlfriends(currentUserId);
        setGirlfriends(girlfriends);

        // Load groups
        const groupResponse = await api.getGroups(currentUserId);
        if (groupResponse.groups) {
          setGroups(groupResponse.groups);
        }
      } catch (error) {
        console.error('Failed to load initial data:', error);
      } finally {
        setIsLoading(false);
      }
    };

    loadInitialData();
  }, [currentUserId, setGirlfriends, setGroups, setCurrentUser]);

  // Restore chat sessions from localStorage
  useEffect(() => {
    const restoreSessions = () => {
      const savedState = localStorage.getItem(`chat_state_${currentUserId}`);
      if (savedState) {
        try {
          const state = JSON.parse(savedState);

          // Restore conversations
          Object.entries(state).forEach(([chatId, sessionData]: [string, any]) => {
            if (sessionData.sessionId) {
              useChatStore.getState().setConversation(chatId, {
                sessionId: sessionData.sessionId,
                messages: [],
              });
            }
          });
        } catch (e) {
          console.error('Failed to restore chat state:', e);
        }
      }
    };

    restoreSessions();
  }, [currentUserId]);

  if (isLoading) {
    return (
      <div className="h-screen flex items-center justify-center bg-gradient-to-br from-pink-50 via-purple-50 to-blue-50">
        <div className="text-center">
          <div className="w-16 h-16 border-4 border-pink-200 border-t-pink-500 rounded-full animate-spin mx-auto mb-4 shadow-lg" />
          <p className="text-gray-600 font-medium">加载中...</p>
          <p className="text-gray-400 text-sm mt-2">AI女友聊天系统</p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-screen flex flex-col">
      <TopBar />
      <div className="flex-1 flex overflow-hidden">
        <Sidebar />
        <ChatArea />
      </div>
    </div>
  );
}

export default App;
