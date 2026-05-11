/**
 * Input Component - 优化版本
 * 改进边框、焦点状态、错误状态
 */

import type { InputHTMLAttributes, TextareaHTMLAttributes } from 'react';
import { forwardRef } from 'react';
import { clsx } from 'clsx';

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  error?: string;
  label?: string;
  helperText?: string;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ className, error, label, helperText, id, ...props }, ref) => {
    return (
      <div className="w-full">
        {label && (
          <label
            htmlFor={id}
            className="block text-sm font-semibold text-gray-700 mb-2"
          >
            {label}
          </label>
        )}
        <input
          ref={ref}
          id={id}
          className={clsx(
            // 基础样式
            'w-full px-4 py-3 rounded-xl border-2 text-gray-900 placeholder-gray-400',
            // 焦点状态
            'focus:outline-none focus:ring-2 focus:ring-pink-500 focus:border-pink-500',
            'transition-all duration-200',
            // 悬停状态
            'hover:border-pink-300',
            // 错误状态
            error
              ? 'border-red-300 focus:ring-red-500 focus:border-red-500'
              : 'border-gray-200',
            // 禁用状态
            'disabled:opacity-50 disabled:cursor-not-allowed disabled:bg-gray-50',
            className
          )}
          {...props}
        />
        {helperText && !error && (
          <p className="mt-1.5 text-sm text-gray-500">{helperText}</p>
        )}
        {error && (
          <p className="mt-1.5 text-sm text-red-500 flex items-center gap-1">
            <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a4 4 0 11-8 0 4 4 0 018 0z" />
            </svg>
            {error}
          </p>
        )}
      </div>
    );
  }
);

Input.displayName = 'Input';

export interface TextareaProps extends Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, 'onChange'> {
  error?: string;
  label?: string;
  autoResize?: boolean;
  helperText?: string;
  onChange?: (e: React.ChangeEvent<HTMLTextAreaElement>) => void;
}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(
  (
    { className, error, label, id, autoResize = false, helperText, onChange, ...props },
    ref
  ) => {
    const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
      if (autoResize && e.target) {
        e.target.style.height = 'auto';
        e.target.style.height = `${e.target.scrollHeight}px`;
      }
      onChange?.(e);
    };

    return (
      <div className="w-full">
        {label && (
          <label
            htmlFor={id}
            className="block text-sm font-semibold text-gray-700 mb-2"
          >
            {label}
          </label>
        )}
        <textarea
          ref={ref}
          id={id}
          rows={4}
          className={clsx(
            // 基础样式
            'w-full px-4 py-3 rounded-xl border-2 text-gray-900 placeholder-gray-400',
            // 焦点状态
            'focus:outline-none focus:ring-2 focus:ring-pink-500 focus:border-pink-500',
            'transition-all duration-200',
            // 悬停状态
            'hover:border-pink-300',
            // 错误状态
            error
              ? 'border-red-300 focus:ring-red-500 focus:border-red-500'
              : 'border-gray-200',
            // 禁用状态
            'disabled:opacity-50 disabled:cursor-not-allowed disabled:bg-gray-50',
            className
          )}
          onChange={handleChange}
          {...props}
        />
        {helperText && !error && (
          <p className="mt-1.5 text-sm text-gray-500">{helperText}</p>
        )}
        {error && (
          <p className="mt-1.5 text-sm text-red-500 flex items-center gap-1">
            <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a4 4 0 11-8 0 4 4 0 018 0z" />
            </svg>
            {error}
          </p>
        )}
      </div>
    );
  }
);

Textarea.displayName = 'Textarea';
