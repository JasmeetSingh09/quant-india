/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        brand: {
          50:  '#f0fdf4',
          100: '#dcfce7',
          500: '#22c55e',
          600: '#16a34a',
          700: '#15803d',
          900: '#14532d',
        }
      },
      // Small text contrast (bug hunt V4-08, 18 Nov 2026). The app sets labels,
      // notes and disclaimers in text-gray-500/600/700, which measure 4.16,
      // 2.66 and 1.9 : 1 on the gray-950 page: "Not financial advice" was the
      // hardest line on the site to read. Text only, so borders, bars and
      // fills keep their shade; one token change here instead of ~600 class
      // edits. 500 now renders at gray-400 (#9ca3af, 7.9 : 1 on gray-950);
      // 600 and 700, the app's quieter notes, one step darker at #8b93a0
      // (6.5 : 1 on gray-950, 5.7 on gray-900, 4.7 on gray-800), so a note
      // still reads below its label and every step stays above AA.
      textColor: {
        gray: {
          500: '#9ca3af',
          600: '#8b93a0',
          700: '#8b93a0',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      }
    }
  },
  plugins: []
}
