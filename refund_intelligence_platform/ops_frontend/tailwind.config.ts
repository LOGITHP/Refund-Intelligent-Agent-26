import type { Config } from 'tailwindcss';

const config: Config = {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: [
          '-apple-system',
          'BlinkMacSystemFont',
          "'Segoe UI'",
          'Roboto',
          'Helvetica',
          'Arial',
          'sans-serif',
        ],
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'Monaco', 'Consolas', 'monospace'],
      },
      colors: {
        shipkart: {
          navy: '#0f233a',
          navyHover: '#1c3553',
          blue: '#2874f0',
          blueHover: '#1d5ec9',
          yellow: '#ffe11b',
          bg: '#f4f6f9',
        },
        canvas: '#f4f6f9',
        rail: '#0f233a',
      },
    },
  },
  plugins: [],
};

export default config;
