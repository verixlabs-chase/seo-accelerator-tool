/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "Segoe UI", "sans-serif"],
      },
      colors: {
        graphite: {
          950: "#090909",
          900: "#101010",
          850: "#141414",
          800: "#181818",
        },
        accent: {
          500: "#FF6A1A",
          600: "#FF7F3F",
          700: "#E85B11",
        },
      },
      boxShadow: {
        panel: "0 0 0 1px rgba(255,255,255,0.04)",
        accent: "0 0 0 1px rgba(255,106,26,0.22), 0 0 30px rgba(255,106,26,0.08)",
      },
    },
  },
  plugins: [],
};
