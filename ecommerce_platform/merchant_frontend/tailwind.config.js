/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        seller: {
          navy: '#0f233a',
          navyHover: '#1c3553',
          blue: '#2874f0',
          yellow: '#ffe11b',
          bg: '#f4f6f9',
        }
      }
    },
  },
  plugins: [],
}

