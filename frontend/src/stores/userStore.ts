/**
 * User Store - Manages current user state
 */

import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface UserState {
  currentUserId: string;
  setUserId: (userId: string) => void;
}

export const useUserStore = create<UserState>()(
  persist(
    (set) => ({
      currentUserId: 'user_001',
      setUserId: (userId) => set({ currentUserId: userId }),
    }),
    {
      name: 'user-storage',
    }
  )
);
