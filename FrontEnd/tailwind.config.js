/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        "slate-blue": "#5b7d96",
        "slate-dark": "#4a6a82",
        "slate-deeper": "#3d5a6e",
        tan: "#c4a882",
        "tan-dark": "#b0936a",
        brown: "#8b5e3c",
        "brown-dark": "#6e4a2e",
      },
      fontFamily: {
        serif: ["Georgia", "Cambria", '"Times New Roman"', "serif"],
        sans: ["Inter", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};
