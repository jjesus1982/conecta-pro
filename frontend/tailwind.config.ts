import type { Config } from 'tailwindcss';

const config: Config = {
  darkMode: 'class',
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        // Conecta Mais - Azul Marinho (Principal)
        navy: {
          50: '#eef4ff',
          100: '#d9e5ff',
          200: '#bcd2ff',
          300: '#8eb6ff',
          400: '#598eff',
          500: '#3366ff',
          600: '#1a47f5',
          700: '#1436e1',
          800: '#172db6',
          900: '#192b8f',
          950: '#111b57',
        },
        // Conecta Mais - Laranja (Destaque)
        brand: {
          50: '#fff8eb',
          100: '#ffecc6',
          200: '#ffd688',
          300: '#ffba4a',
          400: '#ff9f20',
          500: '#f97707',
          600: '#dd5502',
          700: '#b73a06',
          800: '#942c0c',
          900: '#7a260d',
          950: '#461102',
        },
        // Cores de estado
        success: {
          500: '#22c55e',
          600: '#16a34a',
        },
        warning: {
          500: '#f97707',
          600: '#dd5502',
        },
        danger: {
          500: '#ef4444',
          600: '#dc2626',
        },
      },
      fontFamily: {
        sans: ['Geist', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
        display: ['var(--font-display)', 'Space Grotesk', 'system-ui', 'sans-serif'],
        data: ['var(--font-data)', 'IBM Plex Mono', 'monospace'],
      },
      backgroundImage: {
        'gradient-brand': 'linear-gradient(135deg, #1a47f5 0%, #f97707 100%)',
        'gradient-brand-subtle': 'linear-gradient(135deg, rgba(26, 71, 245, 0.1) 0%, rgba(249, 119, 7, 0.1) 100%)',
      },
      animation: {
        'fade-in': 'fadeIn 0.3s ease-out',
        'slide-up': 'slideUp 0.4s ease-out',
        'pulse-slow': 'pulse-slow 2s ease-in-out infinite',
        'shimmer': 'shimmer 1.5s infinite',
        'wag': 'wag 0.5s ease-in-out infinite',
      },
      keyframes: {
        fadeIn: {
          from: { opacity: '0' },
          to: { opacity: '1' },
        },
        slideUp: {
          from: { opacity: '0', transform: 'translateY(10px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
        'pulse-slow': {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.6' },
        },
        shimmer: {
          '0%': { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
        wag: {
          '0%, 100%': { transform: 'rotate(-15deg)' },
          '50%': { transform: 'rotate(15deg)' },
        },
      },
    },
  },
  plugins: [],
};

export default config;
