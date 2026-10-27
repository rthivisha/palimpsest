/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
    "./frontend/index.html",
    "./frontend/src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        cyber: {
          bg: '#090d16',
          surface: '#111827',
          card: '#161f30',
          border: '#1f293d',
          accent: '#06b6d4',      // Electric cyan accent
          accentHover: '#0891b2',
          proven: '#10b981',      // Emerald green for verified
          provenBg: 'rgba(16, 185, 129, 0.12)',
          rejected: '#ef4444',    // Ruby red for rejected/invalid
          rejectedBg: 'rgba(239, 68, 68, 0.12)',
          text: '#f1f5f9',
          muted: '#94a3b8',
        }
      },
      fontFamily: {
        mono: ['JetBrains Mono', 'Fira Code', 'Consolas', 'monospace'],
      }
    },
  },
  plugins: [],
}

