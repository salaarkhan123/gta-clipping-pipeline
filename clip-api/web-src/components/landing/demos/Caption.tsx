import "@fontsource/anton/400.css";
import s from "./demos.module.css";

// The caption styles the renderer draws (CaptionStyle in app/render_options.py), by the name the app shows, with
// the most words and characters each puts on one line (app/pipeline/captions.py). `key`: one keyword is coloured.
export const CAPTION_STYLES = [
  { id: "impact", words: 2, chars: 12, key: true }, { id: "pop", words: 3, chars: 18 }, { id: "bold", words: 3, chars: 18 },
  { id: "neon", words: 3, chars: 18 }, { id: "boxed", words: 3, chars: 18 }, { id: "clean", words: 5, chars: 30 },
  { id: "bounce", words: 3, chars: 18 }, { id: "karaoke", words: 4, chars: 22 }, { id: "reveal", words: 4, chars: 22 },
  { id: "outline", words: 3, chars: 18 }, { id: "subtitle", words: 8, chars: 42 }, { id: "tag", words: 3, chars: 18, key: true },
] as const;
export type CaptionStyle = (typeof CAPTION_STYLES)[number]["id"];
export const styleName = (id: string) => id.charAt(0).toUpperCase() + id.slice(1);

export type Timed = { start: number; end: number; text: string };

// The renderer's line rules (captions.py group_words / group_impact): a line ends at a pause of 0.35 s, after
// punctuation, or when it is full. Returns each line as word indices.
const PAUSE = 0.35, PUNCT = ".,!?;:…", IMPACT_SHORT = 12;
export function linesFor(style: CaptionStyle, words: Timed[]): number[][] {
  const st = CAPTION_STYLES.find((c) => c.id === style)!, out: number[][] = [];
  let cur: number[] = [];
  words.forEach((w, i) => {
    if (cur.length) {
      const prev = words[cur[cur.length - 1]];
      const hard = w.start - prev.end >= PAUSE || PUNCT.includes(prev.text.trim().slice(-1));
      const texts = [...cur.map((j) => words[j].text.trim()), w.text.trim()];
      const full = style === "impact"
        ? !(cur.length < 2 || (cur.length === 2 && texts.join("").length <= IMPACT_SHORT))
        : cur.length >= st.words || texts.join(" ").length > st.chars;
      if (hard || full) { out.push(cur); cur = []; }
    }
    cur.push(i);
  });
  if (cur.length) out.push(cur);
  return out;
}

// The keyword of a line (captions.py keyword): its longest word that is not a stop word.
const STOP = new Set(`a an the and or but so if then than that this these those there here i me my mine myself we us our
ours you your yours yourself he him his she her hers it its they them their theirs i'm i've i'd i'll you're you've you'd
you'll he's she's it's we're we've we'd we'll they're they've they'd they'll that's there's here's what's who's let's im ive
youre thats theres whats lets is am are was were be been being do does did doing done have has had having will would can
could shall should may might must don't doesn't didn't can't couldn't won't wouldn't shouldn't isn't aren't wasn't weren't
haven't hasn't hadn't ain't dont doesnt didnt cant couldnt wont wouldnt shouldnt isnt arent wasnt werent havent hasnt
hadnt aint not no nor yes yeah yep nope ok okay oh ah uh um hmm hey hi well to of in on at by for with from into onto out
up down off over under about as just like really very too also only even still again now get got gonna gotta wanna go
going what who whom which when where why how all any some each both more most much many`.split(/\s+/));
function keyword(texts: string[]): number | null {
  let best: number | null = null, length = 0;
  texts.forEach((t, i) => {
    const bare = t.toLowerCase().replace(/’/g, "'").replace(/[^a-z0-9']/g, "").replace(/^'+|'+$/g, "");
    if (bare && !STOP.has(bare) && bare.length > length) { best = i; length = bare.length; }
  });
  return best;
}

const STILL = ["outline", "subtitle", "clean"];
const shown = (style: CaptionStyle, text: string) => {
  const t = text.trim().replace(/^[^\p{L}\p{N}']+|[^\p{L}\p{N}'!?]+$/gu, "");
  return style === "tag" ? t.toLowerCase() : style === "clean" || style === "subtitle" ? t : t.toUpperCase();
};

// One caption on screen: the line of `words` that holds word `at`, drawn the way `style` draws it. `at` = -1
// draws nothing (no one is talking).
export function Caption({ style, words, at, className = "" }: { style: CaptionStyle; words: Timed[]; at: number; className?: string }) {
  if (at < 0 || !words.length) return null;
  const line = linesFor(style, words).find((l) => l.includes(at)) ?? [];
  const texts = line.map((n) => shown(style, words[n].text));
  const key = style === "impact" || style === "tag" ? keyword(texts) : null;
  const cls = (j: number) => {
    const n = line[j], out = [s.w];
    if (j === key) out.push(s.key);
    if (!STILL.includes(style) && style !== "impact" && style !== "tag" && n === at) out.push(s.on);
    if (style === "karaoke" && n <= at) out.push(s.said);
    if (style === "reveal" && n > at) out.push(s.later);
    return out.join(" ");
  };
  return (
    <span className={`${s.cap} ${s[style]} ${className}`} aria-hidden="true">
      <span className={s.line}>{texts.map((w, j) => <span key={`${line[j]}-${style === "bounce" && line[j] === at ? "on" : ""}`}>{j > 0 && " "}<span className={cls(j)}>{w}</span></span>)}</span>
    </span>
  );
}

// Sample words for frames with no footage yet, timed evenly.
export const sampleWords = (texts: string[], step = 0.38): Timed[] => texts.map((text, i) => ({ start: i * step, end: (i + 1) * step - 0.02, text }));
