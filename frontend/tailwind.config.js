/** ECHOUTRA ONE design tokens. Colors resolve to CSS variables (see src/index.css) so light/dark share one system. */
const v = (name) => `rgb(var(--${name}) / <alpha-value>)`

export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  darkMode: ['class', '[data-theme="dark"]'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"Plus Jakarta Sans Variable"', 'ui-sans-serif', 'system-ui', 'Segoe UI', 'sans-serif'],
      },
      colors: {
        canvas: v('canvas'),
        surface: v('surface'),
        'surface-2': v('surface-2'),
        line: v('line'),
        'line-strong': v('line-strong'),
        ink: v('ink'),
        'ink-2': v('ink-2'),
        muted: v('muted'),
        faint: v('faint'),
        brand: {
          DEFAULT: v('brand'),
          strong: v('brand-strong'),
          soft: v('brand-soft'),
          ink: v('brand-ink'),
        },
        night: { DEFAULT: '#050B0F', 2: '#0A151C', 3: '#112029', line: '#1A2C36' },
        success: { DEFAULT: v('success'), soft: v('success-soft') },
        warning: { DEFAULT: v('warning'), soft: v('warning-soft') },
        danger: { DEFAULT: v('danger'), soft: v('danger-soft') },
        info: { DEFAULT: v('info'), soft: v('info-soft') },
      },
      fontSize: {
        '2xs': ['0.6875rem', { lineHeight: '1rem' }],
      },
      borderRadius: { xl: '0.875rem', '2xl': '1.125rem' },
      boxShadow: {
        card: '0 1px 2px rgb(16 24 32 / 0.04), 0 1px 1px rgb(16 24 32 / 0.02)',
        pop: '0 12px 32px -8px rgb(5 11 15 / 0.18), 0 2px 6px rgb(5 11 15 / 0.06)',
        focus: '0 0 0 3px rgb(var(--brand) / 0.25)',
      },
      keyframes: {
        'fade-up': { from: { opacity: 0, transform: 'translateY(6px)' }, to: { opacity: 1, transform: 'none' } },
        'fade-in': { from: { opacity: 0 }, to: { opacity: 1 } },
        'slide-in': { from: { transform: 'translateX(100%)' }, to: { transform: 'none' } },
        'scale-in': { from: { opacity: 0, transform: 'scale(.97)' }, to: { opacity: 1, transform: 'none' } },
        shimmer: { '100%': { transform: 'translateX(100%)' } },
      },
      animation: {
        'fade-up': 'fade-up .28s cubic-bezier(.2,.7,.3,1) both',
        'fade-in': 'fade-in .2s ease-out both',
        'slide-in': 'slide-in .28s cubic-bezier(.2,.7,.3,1) both',
        'scale-in': 'scale-in .18s cubic-bezier(.2,.7,.3,1) both',
      },
    },
  },
  plugins: [],
}
