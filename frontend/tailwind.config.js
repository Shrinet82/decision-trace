/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        bg: 'var(--color-bg)',
        sidebar: 'var(--color-sidebar)',
        surface: 'var(--color-surface)',
        subtle: 'var(--color-subtle)',
        selected: 'var(--color-selected)',
        hover: 'var(--color-hover)',
        panel: 'var(--color-panel)',
        border: 'var(--color-border)',
        divider: 'var(--color-divider)',
        'row-divider': 'var(--color-row-divider)',
        text: {
          DEFAULT: 'var(--color-text)',
          2: 'var(--color-text-2)',
        },
        muted: 'var(--color-muted)',
        faint: 'var(--color-faint)',
        accent: {
          DEFAULT: 'var(--color-accent)',
          hover: 'var(--color-accent-hover)',
          ring: 'var(--color-accent-ring)',
        },
        status: {
          active: 'var(--status-active)',
          conflict: 'var(--status-conflict)',
          stale: 'var(--status-stale)',
          superseded: 'var(--status-superseded)',
          'stale-text': 'var(--status-stale-text)',
          'conflict-text': 'var(--status-conflict-text)',
          'conflict-bg': 'var(--status-conflict-bg)',
          'conflict-border': 'var(--status-conflict-border)',
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
        xs: ['12px', { lineHeight: '1.45' }],
        sm: ['13px', { lineHeight: '1.45' }],
        base: ['14px', { lineHeight: '1.65' }],
        lg: ['15px', { lineHeight: '1.45' }],
        xl: ['16px', { lineHeight: '1.35' }],
      },
      borderRadius: {
        control: 'var(--radius-control)',
        panel: 'var(--radius-panel)',
        chip: 'var(--radius-chip)',
      },
      boxShadow: {
        composer: 'var(--shadow-composer)',
      },
    },
  },
  plugins: [],
};
