/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  darkMode: ['class', '[data-theme="dark"]'],
  theme: {
    extend: {
      colors: {
        bg: 'var(--color-bg)',
        surface: 'var(--color-surface)',
        'surface-subtle': 'var(--color-surface-subtle)',
        border: 'var(--color-border)',
        text: 'var(--color-text)',
        'text-muted': 'var(--color-text-muted)',
        primary: {
          DEFAULT: 'var(--color-primary)',
          hover: 'var(--color-primary-hover)',
        },
        focus: 'var(--color-focus-ring)',
        danger: {
          DEFAULT: 'var(--color-danger)',
          subtle: 'var(--color-danger-subtle)',
        },
        success: {
          DEFAULT: 'var(--color-success)',
          subtle: 'var(--color-success-subtle)',
        },
        warning: {
          DEFAULT: 'var(--color-warning)',
          subtle: 'var(--color-warning-subtle)',
        },
        line: {
          messaging: 'var(--line-messaging)',
          identity: 'var(--line-identity)',
          data: 'var(--line-data)',
          observability: 'var(--line-observability)',
          platform: 'var(--line-platform)',
        },
      },
      fontFamily: {
        sans: ['var(--font-sans)'],
        mono: ['var(--font-mono)'],
      },
      fontSize: {
        xs: ['var(--text-xs)', { lineHeight: 'var(--leading-ui)' }],
        sm: ['var(--text-sm)', { lineHeight: 'var(--leading-ui)' }],
        base: ['var(--text-base)', { lineHeight: 'var(--leading-ui)' }],
        body: ['var(--text-body)', { lineHeight: 'var(--leading-prose)' }],
        lg: ['var(--text-lg)', { lineHeight: 'var(--leading-ui)' }],
        xl: ['var(--text-xl)', { lineHeight: 'var(--leading-ui)' }],
        '2xl': ['var(--text-2xl)', { lineHeight: 'var(--leading-ui)' }],
      },
      borderRadius: {
        control: 'var(--radius-control)',
        panel: 'var(--radius-panel)',
      },
    },
  },
  plugins: [],
};
