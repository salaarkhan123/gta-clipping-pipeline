import type { Config } from "tailwindcss";

// The ClutchClips look: black, white type, white pill buttons, Geist and Geist Mono. Lime is the one brand accent
// (AI ratings, focus, "on" states). Every colour, font, size, radius and shadow the site uses is a token here;
// app/styles.css and the components read them (`bg-surface`, `text-fg-2`, `text-h2`, `rounded-card`).
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  // The site keeps its own reset (top of app/styles.css); Tailwind's would restyle buttons, images and lists.
  corePlugins: { preflight: false },
  // Utilities always win over the component classes in app/styles.css, whatever their selector weight.
  important: true,
  theme: {
    // Phone-first breakpoints of the site: `narrow` is the phone layout, `tiny` the smallest phones.
    // Max-width queries, largest first, so a smaller screen's rules come later and win.
    screens: { wide: { max: "1360px" }, mid: { max: "1100px" }, narrow: { max: "860px" }, tiny: { max: "420px" } },
    extend: {
      colors: {
        // Surfaces, darkest first.
        bg: "#000000", "bg-2": "#0a0a0a", panel: "#0f0f0f", card: "#141414", surface: "#191919", "card-2": "#1f1f1f", raised: "#262626",
        chip: "#1f1f1f", "chip-hover": "#2a2a2a",
        // Lines: hairlines are white at low opacity so they read the same on every surface.
        line: "rgba(255,255,255,.1)", "line-soft": "rgba(255,255,255,.06)", "line-strong": "rgba(255,255,255,.18)",
        // Text: fg is headings, fg-2 body copy and nav, fg-3 hints.
        text: "#fafafa", fg: "#ffffff", "fg-2": "rgba(255,255,255,.5)", "fg-3": "rgba(255,255,255,.35)",
        muted: "#a1a1a1", dim: "#5c5c5c", soft: "#d4d4d4", label: "#e2e3e7",
        // Buttons: the primary button is a white pill with black text.
        btn: "#fafafa", "btn-hover": "#e5e5e5", "btn-ink": "#000000",
        // Brand accent and states.
        lime: "#b8ff3c", "lime-2": "#7dff8a", cyan: "#3cf0ff", ink: "#0a0d05", danger: "#ff5c7a", warn: "#ffb648",
        "lime-wash": "rgba(184,255,60,.12)", "cyan-wash": "rgba(60,240,255,.10)",
      },
      fontFamily: {
        sans: ["var(--font-geist-sans)", "system-ui", "sans-serif"],
        mono: ["var(--font-geist-mono)", "ui-monospace", "monospace"],
        // Older names, kept so existing classes and theme() calls read Geist too.
        display: ["var(--font-geist-sans)", "system-ui", "sans-serif"],
        body: ["var(--font-geist-sans)", "system-ui", "sans-serif"],
      },
      // Type scale. Each step shrinks to its phone size on its own (clamp), so no breakpoint is needed.
      fontSize: {
        display: ["clamp(28px, 5vw + 8px, 60px)", { lineHeight: "1.0", letterSpacing: "-0.04em", fontWeight: "600" }],
        h2: ["clamp(24px, 3.2vw + 2px, 48px)", { lineHeight: "1.08", letterSpacing: "-0.033em", fontWeight: "600" }],
        h3: ["clamp(18px, 1.2vw + 7px, 24px)", { lineHeight: "1.12", letterSpacing: "-0.03em", fontWeight: "600" }],
        title: ["18px", { lineHeight: "1.4", fontWeight: "600" }],
        lead: ["clamp(16px, 1vw + 6px, 20px)", { lineHeight: "1.5", letterSpacing: "-0.04em", fontWeight: "400" }],
        "body-lg": ["16px", { lineHeight: "1.5", letterSpacing: "-0.03em" }],
        body: ["14px", { lineHeight: "1.3" }],
        eyebrow: ["clamp(12px, .5vw + 9px, 16px)", { lineHeight: "1.25", letterSpacing: "0.0125em", fontWeight: "600" }],
        caption: ["12px", { lineHeight: "1.3" }],
      },
      // Named by size or by role: Tailwind already uses s, e, l, r, t and b for one-side radii.
      borderRadius: { "8": "8px", "12": "12px", "16": "16px", "18": "18px", "20": "20px", "24": "24px", card: "20px", stage: "24px", pill: "1000px" },
      boxShadow: {
        bar: "0 12px 40px rgba(0,0,0,.6), inset 0 0 0 1px rgba(255,255,255,.1)",
        card: "inset 0 0 0 1px rgba(255,255,255,.06)",
        pop: "0 20px 50px rgba(0,0,0,.55)",
      },
      spacing: { rail: "76px", topbar: "56px", tabbar: "64px", nav: "80px", gutter: "16px", section: "120px" },
      maxWidth: { site: "1200px", dash: "1100px", home: "940px", wide: "1680px", prose: "800px" },
      transitionTimingFunction: { out: "cubic-bezier(.2,.8,.2,1)" },
      keyframes: {
        rise: { from: { opacity: "0", transform: "translateY(16px)" }, to: { opacity: "1", transform: "none" } },
      },
      animation: { rise: "rise .6s cubic-bezier(.2,.8,.2,1) both" },
    },
  },
  plugins: [],
};
export default config;
