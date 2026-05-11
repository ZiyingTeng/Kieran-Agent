/**
 * Tabs Component - Large, prominent tabs for sidebar
 */

import { clsx } from 'clsx';

export interface Tab {
  id: string;
  label: string;
  icon?: React.ReactNode;
  disabled?: boolean;
}

export interface TabsProps {
  tabs: Tab[];
  activeTab: string;
  onChange: (tabId: string) => void;
  className?: string;
}

export function Tabs({ tabs, activeTab, onChange, className }: TabsProps) {
  return (
    <div className={clsx('flex gap-2 p-2', className)}>
      {tabs.map((tab) => (
        <button
          key={tab.id}
          onClick={() => !tab.disabled && onChange(tab.id)}
          disabled={tab.disabled}
          className={clsx(
            'flex-1 flex items-center justify-center gap-2 px-4 py-3 rounded-xl text-base font-semibold transition-all duration-200',
            activeTab === tab.id
              ? 'bg-gradient-to-r from-[#ff6b9d] to-[#c44569] text-white shadow-lg shadow-pink-200 transform scale-105'
              : 'bg-gray-100 text-gray-600 hover:bg-gray-200 hover:text-gray-800',
            tab.disabled && 'opacity-50 cursor-not-allowed'
          )}
        >
          {tab.icon && <span>{tab.icon}</span>}
          <span>{tab.label}</span>
        </button>
      ))}
    </div>
  );
}
