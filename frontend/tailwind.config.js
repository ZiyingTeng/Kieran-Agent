/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // 主色调 - 优化后的粉色系
        primary: '#f472b6',
        secondary: '#ec4899',
        accent: '#8b5cf6',
        accent2: '#a855f7',

        // 语义化颜色
        success: '#10b981',
        warning: '#f59e0b',
        danger: '#ef4444',
        info: '#3b82f6',

        // 背景色
        'bg-primary': '#fdf2f8',
        'bg-secondary': '#faf5ff',
        'bg-accent': '#f5f3ff',

        // 边框色
        'border-primary': '#fce7f3',
        'border-secondary': '#f3e8ff',

        // 文字颜色
        'text-primary': '#1f2937',
        'text-secondary': '#6b7280',
        'text-muted': '#9ca3af',
      },
      animation: {
        'fade-in': 'fadeIn 0.3s ease',
        'slide-up': 'slideUp 0.3s ease',
        'slide-in': 'slideIn 0.3s ease',
        'pulse-slow': 'pulse 2s infinite',
        'shimmer': 'shimmer 2s infinite',
        'bounce-slow': 'bounce 2s infinite',
      },
      keyframes: {
        fadeIn: {
          'from': { opacity: '0' },
          'to': { opacity: '1' },
        },
        slideUp: {
          'from': { transform: 'translateY(20px)', opacity: '0' },
          'to': { transform: 'translateY(0)', opacity: '1' },
        },
        slideIn: {
          'from': { transform: 'translateX(100%)', opacity: '0' },
          'to': { transform: 'translateX(0)', opacity: '1' },
        },
        shimmer: {
          '0%': { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
      },
      boxShadow: {
        'glow': '0 0 20px rgba(244, 114, 182, 0.3)',
        'glow-lg': '0 0 30px rgba(244, 114, 182, 0.4)',
      },
    },
  },
  plugins: [],
}
