/**
 * GirlfriendItem Component - Enhanced with better styling
 */

import type { Girlfriend } from '@/types';
import { Avatar, Dropdown } from '@/components/ui';
import type { DropdownItem } from '@/components/ui';
import { clsx } from 'clsx';

export interface GirlfriendItemProps {
  girlfriend: Girlfriend;
  isActive?: boolean;
  onClick: () => void;
  onEdit?: () => void;
  onDelete?: () => void;
}

export function GirlfriendItem({
  girlfriend,
  isActive = false,
  onClick,
  onEdit,
  onDelete,
}: GirlfriendItemProps) {
  const isCustom = !girlfriend.is_system;

  const menuItems: DropdownItem[] = [];
  if (isCustom && onEdit) {
    menuItems.push({
      id: 'edit',
      label: '编辑角色',
      icon: (
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
        </svg>
      ),
      onClick: onEdit,
    });
  }
  if (isCustom && onDelete) {
    menuItems.push({
      id: 'delete',
      label: '删除角色',
      danger: true,
      divider: menuItems.length > 0,
      icon: (
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
        </svg>
      ),
      onClick: onDelete,
    });
  }

  return (
    <div
      onClick={onClick}
      className={clsx(
        'group flex items-center gap-4 px-5 py-4 cursor-pointer transition-all duration-200',
        'border-l-4',
        'hover:bg-gradient-to-r hover:from-pink-50 hover:to-transparent',
        isActive
          ? 'bg-gradient-to-r from-pink-50 to-white border-pink-500 shadow-inner'
          : 'border-transparent hover:border-pink-300'
      )}
    >
      <Avatar
        name={girlfriend.name}
        size="xl"
        variant={girlfriend.is_system ? 'system' : 'custom'}
        className="shadow-lg"
      />
      <div className="flex-1 min-w-0">
        <p
          className={clsx(
            'text-base font-semibold truncate',
            isActive ? 'text-pink-600' : 'text-gray-900'
          )}
        >
          {girlfriend.name}
        </p>
        {girlfriend.description && (
          <p className="text-sm text-gray-500 truncate mt-0.5">
            {girlfriend.description}
          </p>
        )}
      </div>
      {isCustom && menuItems.length > 0 ? (
        <div
          className="opacity-0 group-hover:opacity-100 transition-opacity"
          onClick={(e) => e.stopPropagation()}
        >
          <Dropdown
            trigger={
              <button className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400 hover:text-gray-600">
                <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                  <path d="M10 6a2 2 0 110-4 2 2 0 010 4zM10 12a2 2 0 110-4 2 2 0 010 4zM10 18a2 2 0 110-4 2 2 0 010 4z" />
                </svg>
              </button>
            }
            items={menuItems}
          />
        </div>
      ) : isActive ? (
        <span className="text-pink-500">
          <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
          </svg>
        </span>
      ) : null}
    </div>
  );
}
