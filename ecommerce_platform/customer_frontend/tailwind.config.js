/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        fk: {
          blue: '#2874f0',
          darkBlue: '#1c5cc5',
          yellow: '#ffe11b',
          orange: '#fb641b',
          gray: '#f1f3f6',
          dark: '#212121',
          muted: '#878787',
          green: '#388e3c',
        }
      }
    },
  },
  plugins: [],
}

