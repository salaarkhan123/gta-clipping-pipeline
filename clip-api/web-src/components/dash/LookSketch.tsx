import { hasPanels } from "@/lib/templates";

const SINGLE = ["full", "fit", "fill", "pip", "classic"];
const shape = (aspect: string) => { const [w, h] = aspect.split(":").map(Number); return w > 0 && h > 0 ? w / h : 9 / 16; };

// Our own drawing of a clip's look, used wherever a template has no picture: the panels at their real
// proportions (camera and gameplay), and a caption where it will sit, drawn the way its style renders.
// Nothing here is footage. `reframed: false` draws the source's own wide frame.
export function LookSketch({ aspect = "9:16", layout = "auto", camera, split, captions = true, style, reframed = true }: {
  aspect?: string; layout?: string; camera?: string | null; split?: number | null; captions?: boolean; style?: string; reframed?: boolean }) {
  const one = !reframed || SINGLE.includes(layout) || aspect === "16:9" && !hasPanels(layout);
  // With no panel sizes given: the camera over the gameplay, the way an automatic split usually falls.
  const top = camera || "top", share = Math.round((split ?? (top === "top" ? 0.38 : 0.6)) * 100);
  const ratio = reframed ? shape(aspect) : 16 / 9;
  return (
    <span className={`mock ${captions && style ? `cap-${style}` : ""}`}
      style={{ aspectRatio: ratio, "--r": ratio, gridTemplateRows: one ? "1fr" : `${share}% 1fr` } as React.CSSProperties}>
      {one ? <i className="game" /> : <><i className={top === "top" ? "cam" : "game"} /><i className={top === "top" ? "game" : "cam"} /></>}
      {reframed && layout === "pip" && <i className="cam inset" />}
      {captions && <b style={{ top: one ? "72%" : `${share}%` }}>No <u>way</u></b>}
    </span>
  );
}
