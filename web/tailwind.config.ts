import type { Config } from "tailwindcss";

// Semantic tokens only (docs/BRIEF.md "Brand"). Components never use raw hex values.
const token = (name: string) => `rgb(var(--${name}) / <alpha-value>)`;

export default {
  darkMode: "class",
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: token("bg"),
        card: token("card"),
        line: token("line"),
        muted: token("muted"),
        text: token("text"),
        primary: token("primary"),
        "on-primary": token("on-primary"),
        accent: token("accent"),
      },
      fontFamily: {
        display: ["var(--font-display)", "system-ui", "sans-serif"],
        sans: ["var(--font-body)", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
} satisfies Config;
