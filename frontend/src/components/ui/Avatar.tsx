/**
 * Avatar Component
 */

import { clsx } from 'clsx';

export interface AvatarProps {
  src?: string;
  alt?: string;
  name?: string;
  size?: 'sm' | 'md' | 'lg' | 'xl' | '2xl';
  variant?: 'primary' | 'secondary' | 'system' | 'custom' | 'group';
  className?: string;
}

const sizeStyles = {
  sm: 'w-8 h-8 text-xs',
  md: 'w-10 h-10 text-sm',
  lg: 'w-12 h-12 text-base',
  xl: 'w-16 h-16 text-lg',
  '2xl': 'w-20 h-20 text-xl',
};

const gradientStyles = {
  primary: 'bg-gradient-to-br from-[#ff6b9d] to-[#c44569]',
  secondary: 'bg-gradient-to-br from-[#667eea] to-[#764ba2]',
  system: 'bg-gradient-to-br from-[#667eea] to-[#764ba2]',
  custom: 'bg-gradient-to-br from-[#f093fb] to-[#f5576c]',
  group: 'bg-gradient-to-br from-[#667eea] to-[#764ba2]',
};

export function Avatar({
  src,
  alt,
  name,
  size = 'md',
  variant = 'primary',
  className,
}: AvatarProps) {
  const getInitials = (name?: string) => {
    if (!name) return '';
    const words = name.trim().split(/\s+/);
    if (words.length === 1) {
      return words[0].charAt(0).toUpperCase();
    }
    return (words[0].charAt(0) + words[words.length - 1].charAt(0)).toUpperCase();
  };

  const getContent = () => {
    if (src) {
      return <img src={src} alt={alt || name || 'Avatar'} className="w-full h-full object-cover rounded-full" />;
    }
    return <span className="font-semibold">{getInitials(name)}</span>;
  };

  const getEmoji = () => {
    switch (variant) {
      case 'group':
        return '👥';
      default:
        return null;
    }
  };

  const emoji = getEmoji();
  const hasGradient = !src && !emoji;

  return (
    <div
      className={clsx(
        'flex items-center justify-center rounded-full text-white font-semibold flex-shrink-0 shadow-sm',
        sizeStyles[size],
        hasGradient && gradientStyles[variant],
        !hasGradient && !src && 'bg-gray-200 text-gray-600',
        className
      )}
    >
      {emoji || getContent()}
    </div>
  );
}
