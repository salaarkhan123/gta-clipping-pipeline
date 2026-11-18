import type { Config } from "tailwindcss";

// The ClutchClips brand: dark, lime and cyan, Poppins for headings, Inter for text. Every colour, font and size
// the site uses is a token here; app/styles.css and the components read them (`bg-panel`, `theme(colors.line)`).
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  // Our own reset lives in app/styles.css (@layer base); Tailwind's would restyle buttons, images and lists.
  corePlugins: { preflight: false },
  theme: {
    // Phone-first breakpoints of the site: `narrow` is the phone layout, `tiny` the smallest phones.
    screens: { tiny: { max: "420px" }, narrow: { max: "860px" }, mid: { max: "1100px" }, wide: { max: "1360px" } },
    extend: {
      colors: {
        bg: "#07080a", "bg-2": "#0d0f12", card: "#121418", "card-2": "#181b20", line: "#23272e", "line-soft": "#1c2026",
        panel: "#0f1114", chip: "#1a1d22", "chip-hover": "#22262c",
        text: "#f4f6f8", muted: "#9aa3ad", dim: "#59616b", soft: "#c9cfd6", label: "#d6dbe0",
        lime: "#b8ff3c", "lime-2": "#7dff8a", cyan: "#3cf0ff", ink: "#0a0d05", danger: "#ff5c7a", warn: "#ffb648",
        "lime-wash": "rgba(184,255,60,.12)", "cyan-wash": "rgba(60,240,255,.10)",
      },
      fontFamily: {
        display: ["Poppins", "system-ui", "sans-serif"],
        body: ["Inter", "system-ui", "sans-serif"],
      },
      borderRadius: { s: "8px", m: "12px", l: "16px", xl2: "18px", xl3: "20px" },
      spacing: { rail: "76px", topbar: "56px", tabbar: "64px" },
      maxWidth: { site: "1200px", dash: "1100px", home: "940px", wide: "1680px" },
    },
  },
  plugins: [],
};
export default config;
