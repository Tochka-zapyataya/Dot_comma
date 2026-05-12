/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          orange: "#F26522",
          "orange-deep": "#D9551A",
          "orange-light": "#FF8B4D",
          "orange-soft": "#FFE7D6",
          yellow: "#FFC72C",
          "yellow-soft": "#FFF1B8",
          forest: "#0F3D2A",
          "forest-deep": "#0A2A1D",
          "forest-light": "#1A5638",
          "forest-soft": "#E5EFE8",
          green: "#0E8C3A",
          "green-deep": "#0a6b2c",
          red: "#D32F2F",
        },
        graphite: {
          50: "#f6f7f8",
          100: "#eceef1",
          200: "#d6dade",
          300: "#b3bac1",
          400: "#828a93",
          500: "#5c6571",
          600: "#3f4753",
          700: "#2c333d",
          800: "#1f242c",
          900: "#141820",
        },
        base: {
          bg: "#FAF7F2",
          card: "#ffffff",
        },
        status: {
          exact: "#0E8C3A",
          okPlus: "#FFC72C",
          bad: "#D32F2F",
          none: "#9ca3af",
        },
      },
      boxShadow: {
        soft: "0 6px 24px -8px rgba(20, 24, 32, 0.18)",
        card: "0 2px 8px -2px rgba(20, 24, 32, 0.08), 0 8px 24px -12px rgba(20, 24, 32, 0.10)",
        glow: "0 0 0 4px rgba(242, 101, 34, 0.22)",
        forest: "0 24px 48px -16px rgba(15, 61, 42, 0.45)",
      },
      fontFamily: {
        sans: [
          "Inter",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "sans-serif",
        ],
      },
    },
  },
  plugins: [],
};
