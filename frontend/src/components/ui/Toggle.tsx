/**
 * Toggle Switch Component
 */

import type { ChangeEvent } from 'react';
import { clsx } from 'clsx';

export interface ToggleProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label?: string;
  disabled?: boolean;
  className?: string;
}

export function Toggle({
  checked,
  onChange,
  label,
  disabled = false,
  className,
}: ToggleProps) {
  const handleChange = (e: ChangeEvent<HTMLInputElement>) => {
    onChange(e.target.checked);
  };

  return (
    <label className={clsx('flex items-center gap-2 cursor-pointer', className)}>
      <div className="relative">
        <input
          type="checkbox"
          checked={checked}
          onChange={handleChange}
          disabled={disabled}
          className="sr-only"
        />
        <div
          className={clsx(
            'w-12 h-6 rounded-full transition-colors duration-200 shadow-sm',
            checked ? 'bg-gradient-to-r from-pink-500 to-rose-500' : 'bg-gray-300',
            disabled && 'opacity-50 cursor-not-allowed'
          )}
        >
          <div
            className={clsx(
              'absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full shadow-md transition-transform duration-200',
              checked && 'translate-x-6'
            )}
          />
        </div>
      </div>
      {label && (
        <span className="text-sm text-gray-700 select-none font-medium">{label}</span>
      )}
    </label>
  );
}
