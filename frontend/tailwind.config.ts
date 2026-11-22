import type { Config } from 'tailwindcss';

const config: Config = {
  content: ['./app/**/*.{ts,tsx}', './components/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: '#0b1220',
        panel: '#121a2b',
        line: '#1f2b42',
        accent: '#3b82f6',
        ok: '#10b981',
        warn: '#f59e0b',
        bad: '#ef4444',
      },
    },
  },
  plugins: [],
};
export default config;
