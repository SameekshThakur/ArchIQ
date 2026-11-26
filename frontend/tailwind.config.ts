import type { Config } from 'tailwindcss';

const v = (name: string) => `rgb(var(--${name}) / <alpha-value>)`;

export default {
  darkMode: ['class', '[data-theme="dark"]'],
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        bg: v('bg'),
        surface: v('surface'),
        raised: v('raised'),
        overlay: v('overlay'),
        line: v('border'),
        'line-subtle': v('border-subtle'),
        fg: v('fg'),
        'fg-2': v('fg-2'),
        'fg-3': v('fg-3'),
        accent: v('accent'),
        'accent-2': v('accent-2'),
        'accent-fg': v('accent-fg'),
        critical: v('critical'),
        high: v('high'),
        medium: v('medium'),
        low: v('low'),
        healthy: v('healthy'),
      },
      fontFamily: {
        sans: ['Inter', '"Inter Fallback"', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', '"JetBrains Mono Fallback"', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
      fontSize: {
        micro: ['11px', { lineHeight: '14px', letterSpacing: '0.06em' }],
        xs: ['12px', { lineHeight: '16px' }],
        sm: ['13px', { lineHeight: '18px' }],
        base: ['14px', { lineHeight: '20px' }],
        lg: ['16px', { lineHeight: '22px' }],
        xl: ['20px', { lineHeight: '26px', letterSpacing: '-0.01em' }],
        '2xl': ['24px', { lineHeight: '30px', letterSpacing: '-0.015em' }],
        '3xl': ['32px', { lineHeight: '38px', letterSpacing: '-0.02em' }],
      },
      borderRadius: { sm: '4px', DEFAULT: '6px', md: '8px', lg: '12px' },
      spacing: { 4.5: '18px' },
      boxShadow: {
        pop: '0 12px 32px -8px rgb(0 0 0 / 0.45), 0 0 0 1px rgb(var(--border) / 1)',
        inset: 'inset 0 1px 0 0 rgb(255 255 255 / 0.04)',
      },
      transitionDuration: { 150: '150ms', 180: '180ms', 220: '220ms' },
      keyframes: {
        shimmer: { '100%': { transform: 'translateX(100%)' } },
        pulseDot: {
          '0%': { boxShadow: '0 0 0 0 rgb(var(--healthy) / 0.5)' },
          '70%': { boxShadow: '0 0 0 6px rgb(var(--healthy) / 0)' },
          '100%': { boxShadow: '0 0 0 0 rgb(var(--healthy) / 0)' },
        },
        slideIn: { from: { transform: 'translateX(16px)', opacity: '0' }, to: { transform: 'none', opacity: '1' } },
        fadeIn: { from: { opacity: '0' }, to: { opacity: '1' } },
        rise: { from: { transform: 'translateY(6px)', opacity: '0' }, to: { transform: 'none', opacity: '1' } },
      },
      animation: {
        shimmer: 'shimmer 1.6s infinite',
        pulseDot: 'pulseDot 2s infinite',
        slideIn: 'slideIn 200ms cubic-bezier(.2,.8,.2,1)',
        fadeIn: 'fadeIn 150ms ease-out',
        rise: 'rise 220ms cubic-bezier(.2,.8,.2,1)',
      },
    },
  },
  plugins: [],
} satisfies Config;
