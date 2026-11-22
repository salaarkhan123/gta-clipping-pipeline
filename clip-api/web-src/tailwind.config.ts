import type { Config } from "tailwindcss";

// The ClutchClips look: near-black, white type, Geist and Geist Mono. Lime is the one brand accent (scores, focus,
// "on" states). The values live in app/tokens.css as CSS variables; this file gives them Tailwind names
// (`bg-surface`, `text-fg-2`, `text-h2`, `rounded-card`), and /design shows them all.
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
      // Every colour is a variable from app/tokens.css; the signed-in app overrides them under data-theme="app".
      colors: {
        bg: "var(--canvas)", "bg-2": "var(--canvas-2)", panel: "var(--panel)", card: "var(--card)", surface: "var(--surface)",
        "card-2": "var(--control)", raised: "var(--raised)", chip: "var(--control)", "chip-hover": "var(--control-hover)",
        control: "var(--control)", "control-hover": "var(--control-hover)", "nav-on": "var(--nav-on)",
        line: "var(--line)", "line-soft": "var(--line-soft)", "line-strong": "var(--line-strong)",
        text: "var(--text)", fg: "var(--fg)", "fg-2": "var(--fg-2)", "fg-3": "var(--fg-3)",
        muted: "#a1a1a1", dim: "#5c5c5c", soft: "#d4d4d4", label: "#e2e3e7",
        btn: "var(--btn)", "btn-hover": "var(--btn-hover)", "btn-ink": "var(--btn-ink)",
        // The accent stays a literal here (same value as --accent) so opacity modifiers such as bg-lime/8 keep working.
        lime: "#b8ff3c", "lime-2": "#7dff8a", cyan: "#3cf0ff", ink: "#0a0d05", danger: "#ff5c7a", warn: "#ffb648",
        "lime-wash": "rgba(184,255,60,.12)", "cyan-wash": "rgba(60,240,255,.10)",
      },
      fontFamily: {
        sans: ["var(--font-sans)"],
        mono: ["var(--font-geist-mono)", "ui-monospace", "monospace"],
        // Older names, kept so existing classes and theme() calls read Geist too.
        display: ["var(--font-sans)"],
        body: ["var(--font-sans)"],
      },
      // In the app the heaviest weight is 600 (--weight-bold), so type reads softer; the public site keeps 700.
      fontWeight: { bold: "var(--weight-bold, 700)" },
      // Type scale. Each step shrinks to its phone size on its own (clamp), so no breakpoint is needed.
      fontSize: {
        display: ["var(--text-display)", { lineHeight: "1.04", letterSpacing: "-0.035em", fontWeight: "600" }],
        h2: ["var(--text-h2)", { lineHeight: "1.1", letterSpacing: "-0.03em", fontWeight: "600" }],
        h3: ["var(--text-h3)", { lineHeight: "1.2", letterSpacing: "-0.02em", fontWeight: "600" }],
        title: ["var(--text-title)", { lineHeight: "1.35", letterSpacing: "-0.01em", fontWeight: "600" }],
        lead: ["var(--text-lead)", { lineHeight: "1.5", letterSpacing: "-0.01em", fontWeight: "400" }],
        "body-lg": ["16px", { lineHeight: "1.5", letterSpacing: "-0.01em" }],
        body: ["var(--text-body)", { lineHeight: "1.45" }],
        small: ["var(--text-small)", { lineHeight: "1.4" }],
        eyebrow: ["clamp(12px, .5vw + 9px, 16px)", { lineHeight: "1.25", letterSpacing: "0.0125em", fontWeight: "600" }],
        caption: ["var(--text-caption)", { lineHeight: "1.35" }],
        // Section labels: BASIC, CAPTION STYLES, LAYOUT.
        label: ["var(--text-label)", { lineHeight: "1.2", letterSpacing: "0.08em", fontWeight: "600" }],
      },
      // Named by size or by role: Tailwind already uses s, e, l, r, t and b for one-side radii.
      borderRadius: { "8": "var(--radius-xs)", "12": "var(--radius-sm)", "16": "var(--radius-md)", "18": "18px", "20": "var(--radius-card)", "24": "var(--radius-stage)",
        card: "var(--radius-card)", stage: "var(--radius-stage)", pill: "var(--radius-pill)", control: "var(--radius-control)" },
      boxShadow: {
        bar: "0 12px 40px rgba(0,0,0,.6), inset 0 0 0 1px rgba(255,255,255,.1)",
        card: "inset 0 0 0 1px rgba(255,255,255,.06)",
        pop: "0 20px 50px rgba(0,0,0,.55)",
      },
      spacing: { rail: "76px", topbar: "56px", tabbar: "64px", nav: "72px", gutter: "16px", section: "120px" },
      maxWidth: { site: "1200px", dash: "1100px", home: "940px", wide: "1680px", prose: "800px", stage: "1040px" },
      transitionTimingFunction: { out: "var(--ease-out)", loop: "var(--ease-in-out)" },
      transitionDuration: { fast: "var(--dur-fast)", base: "var(--dur)", slow: "var(--dur-slow)" },
      keyframes: {
        rise: { from: { opacity: "0", transform: "translateY(16px)" }, to: { opacity: "1", transform: "none" } },
      },
      animation: { rise: "rise .6s cubic-bezier(.2,.8,.2,1) both" },
    },
  },
  plugins: [],
};
export default config;
