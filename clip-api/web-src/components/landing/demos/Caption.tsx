import "@fontsource/anton/400.css";
import s from "./demos.module.css";

// The caption styles the renderer draws (CaptionStyle in app/render_options.py), by the name the app shows,
// with how many words each puts on screen at once (app/pipeline/captions.py). `key` styles colour one keyword.
export const CAPTION_STYLES = [
  { id: "impact", words: 2, key: true }, { id: "pop", words: 3 }, { id: "bold", words: 3 }, { id: "neon", words: 3 },
  { id: "boxed", words: 3 }, { id: "clean", words: 5 }, { id: "bounce", words: 3 }, { id: "karaoke", words: 4 },
  { id: "reveal", words: 4 }, { id: "outline", words: 3 }, { id: "subtitle", words: 8 }, { id: "tag", words: 3, key: true },
] as const;
export type CaptionStyle = (typeof CAPTION_STYLES)[number]["id"];
export const styleName = (id: string) => id.charAt(0).toUpperCase() + id.slice(1);

const STILL = ["outline", "subtitle", "clean"];

// One caption on screen: the group of `words` holding word `at`, drawn the way `style` draws it.
export function Caption({ style, words, keys = [], at, className = "" }: {
  style: CaptionStyle; words: string[]; keys?: number[]; at: number; className?: string }) {
  const per = CAPTION_STYLES.find((c) => c.id === style)!.words;
  const i = ((at % words.length) + words.length) % words.length, from = Math.floor(i / per) * per;
  const group = words.slice(from, from + per);
  const cls = (j: number) => {
    const n = from + j, out = [s.w];
    if (keys.includes(n) && (style === "impact" || style === "tag")) out.push(s.key);
    if (!STILL.includes(style) && style !== "impact" && style !== "tag" && n === i) out.push(s.on);
    if (style === "karaoke" && n <= i) out.push(s.said);
    if (style === "reveal" && n > i) out.push(s.later);
    return out.join(" ");
  };
  return (
    <span className={`${s.cap} ${s[style]} ${className}`} aria-hidden="true">
      <span className={s.line}>{group.map((w, j) => <span key={`${style}-${from + j}-${style === "bounce" && from + j === i ? at : ""}`}>{j > 0 && " "}<span className={cls(j)}>{w}</span></span>)}</span>
    </span>
  );
}
