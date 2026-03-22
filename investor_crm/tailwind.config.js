/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './crm/templates/**/*.html',
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"DM Sans"', 'sans-serif'],
      },
      colors: {
        navy: {
          DEFAULT: '#0f1a2e',
          light: '#1a2744',
        },
        /** Dark forest green — dashboard Confirmed stats (distinct from status-confirmed-text badges) */
        forest: {
          DEFAULT: '#14532d',
        },
        grey: {
          DEFAULT: '#5a6578',
          dark: '#7a8494',
          darker: '#9ca3af',
          border: '#e2e6ed',
          'border-light': '#d1d5dc',
          hover: '#f1f3f7',
          card: '#f8f9fb',
        },
        status: {
          'confirmed-bg': '#ecfdf5',
          'confirmed-text': '#059669',
          'confirmed-border': '#a7f3d0',
          'sma-bg': '#fffbeb',
          'sma-text': '#d97706',
          'sma-border': '#fde68a',
          'feeder-bg': '#f5f3ff',
          'feeder-text': '#7c3aed',
          'feeder-border': '#ddd6fe',
          'fund-bg': '#eff6ff',
          'fund-text': '#2563eb',
          'fund-border': '#bfdbfe',
          'other-bg': '#f1f3f7',
          'other-text': '#5a6578',
          'other-border': '#e2e6ed',
        },
        decision: {
          committed: '#059669',
          passed: '#dc2626',
          pending: '#7a8494',
          'committed-bg': '#ecfdf5',
          'committed-border': '#a7f3d0',
          'passed-bg': '#fef2f2',
          'passed-border': '#fecaca',
          'pending-bg': '#f1f3f7',
          'pending-border': '#e2e6ed',
        },
        vdr: {
          active: '#059669',
          inactive: '#d1d5dc',
        },
        accent: '#2563eb',
        danger: {
          DEFAULT: '#dc2626',
          hover: '#b91c1c',
        },
        ageing: {
          amber: '#d97706',
          red: '#dc2626',
        },
        reminder: {
          overdue: '#dc2626',
          upcoming: '#d97706',
          'overdue-bg': '#fef2f2',
          'upcoming-bg': '#fffbeb',
        },
        timeline: {
          call: '#059669',
          'call-bg': '#ecfdf5',
          email: '#2563eb',
          'email-bg': '#eff6ff',
          meeting: '#d97706',
          'meeting-bg': '#fffbeb',
          coinvest: '#7c3aed',
          'coinvest-bg': '#f5f3ff',
        },
      },
      fontSize: {
        'table-header': ['10px', { letterSpacing: '0.06em', fontWeight: '600' }],
        'field-label': ['11px', { letterSpacing: '0.05em', fontWeight: '600' }],
        'body-sm': ['12px', { lineHeight: '1.5' }],
        'body': ['13px', { lineHeight: '1.5' }],
        'heading': ['15px', { fontWeight: '700' }],
        'page-title': ['20px', { fontWeight: '700' }],
      },
      borderRadius: {
        card: '10px',
        table: '8px',
        modal: '12px',
        badge: '20px',
        tag: '4px',
      },
    },
  },
  plugins: [],
};

