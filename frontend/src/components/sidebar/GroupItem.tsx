/**
 * GroupItem Component - Enhanced with better styling
 */

import type { Group } from '@/types';
import { Avatar } from '@/components/ui';
import { clsx } from 'clsx';

export interface GroupItemProps {
  group: Group;
  isActive?: boolean;
  onClick: () => void;
}

export function GroupItem({ group, isActive = false, onClick }: GroupItemProps) {
  return (
    <div
      onClick={onClick}
      className={clsx(
        'flex items-center gap-4 px-5 py-4 cursor-pointer transition-all duration-200',
        'border-l-4',
        'hover:bg-gradient-to-r hover:from-purple-50 hover:to-transparent',
        isActive
          ? 'bg-gradient-to-r from-purple-50 to-white border-purple-500 shadow-inner'
          : 'border-transparent hover:border-purple-300'
      )}
    >
      <Avatar
        name={group.group_name}
        size="xl"
        variant="group"
        className="shadow-lg"
      />
      <div className="flex-1 min-w-0">
        <p
          className={clsx(
            'text-base font-semibold truncate',
            isActive ? 'text-purple-600' : 'text-gray-900'
          )}
        >
          {group.group_name}
        </p>
        <p className="text-sm text-gray-500 flex items-center gap-1 mt-0.5">
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
          </svg>
          {group.members.length} 个成员
        </p>
      </div>
      {isActive && (
        <span className="text-purple-500">
          <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
          </svg>
        </span>
      )}
    </div>
  );
}
