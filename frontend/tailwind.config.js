/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        paper: "#F5F3EE",
        stone: "#ECEAE4",
        ink: "#20231F",
        muted: "#74766F",
        sage: "#81927F",
        forest: "#34483B",
        champagne: "#B29A6A",
      },
      fontFamily: {
        sans: ["DM Sans", "sans-serif"],
        display: ["Manrope", "sans-serif"],
      },
    },
  },
  plugins: [require("@tailwindcss/forms")],
};
