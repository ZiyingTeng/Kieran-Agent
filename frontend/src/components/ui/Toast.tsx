/**
 * Toast Component
 */

import { createRoot } from 'react-dom/client';
import { useEffect, useState } from 'react';
import { clsx } from 'clsx';

type ToastVariant = 'success' | 'error' | 'info' | 'warning';

interface ToastProps {
  message: string;
  variant?: ToastVariant;
  duration?: number;
  onClose?: () => void;
}

const variantStyles = {
  success: 'bg-green-500',
  error: 'bg-red-500',
  info: 'bg-gray-800',
  warning: 'bg-yellow-500',
};

const variantIcons = {
  success: '✓',
  error: '✕',
  info: 'ℹ',
  warning: '⚠',
};

function Toast({ message, variant = 'info', duration = 3000, onClose }: ToastProps) {
  const [isVisible, setIsVisible] = useState(true);

  useEffect(() => {
    const timer = setTimeout(() => {
      setIsVisible(false);
      setTimeout(() => onClose?.(), 300);
    }, duration);

    return () => clearTimeout(timer);
  }, [duration, onClose]);

  return (
    <div
      className={clsx(
        'fixed top-4 right-4 z-[10000] flex items-center gap-3 px-4 py-3 text-white rounded-lg shadow-lg animate-slide-in transition-all duration-300',
        variantStyles[variant],
        isVisible ? 'opacity-100 translate-x-0' : 'opacity-0 translate-x-full'
      )}
    >
      <span className="flex-shrink-0">{variantIcons[variant]}</span>
      <span className="text-sm font-medium">{message}</span>
    </div>
  );
}

let toastContainer: HTMLDivElement | null = null;
let toastRoot: any = null;

function getToastContainer() {
  if (!toastContainer) {
    toastContainer = document.createElement('div');
    toastContainer.id = 'toast-container';
    document.body.appendChild(toastContainer);
    toastRoot = createRoot(toastContainer);
  }
  return { container: toastContainer, root: toastRoot };
}

export const toast = {
  show: (message: string, variant: ToastVariant = 'info', duration?: number) => {
    const { root } = getToastContainer();
    root.render(
      <Toast
        message={message}
        variant={variant}
        duration={duration}
        onClose={() => {
          root.render(null);
        }}
      />
    );
  },
  success: (message: string, duration?: number) => {
    toast.show(message, 'success', duration);
  },
  error: (message: string, duration?: number) => {
    toast.show(message, 'error', duration);
  },
  info: (message: string, duration?: number) => {
    toast.show(message, 'info', duration);
  },
  warning: (message: string, duration?: number) => {
    toast.show(message, 'warning', duration);
  },
};
