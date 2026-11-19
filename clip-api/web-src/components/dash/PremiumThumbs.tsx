"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { creditWords, followJob, useQuote } from "@/lib/exporting";
import { chooseThumb, editThumb, Gallery, loadGallery, newOrderKey, orderPremium, premiumQuotePath, styleName } from "@/lib/thumbs";
import { Icon } from "./Icon";
import { useDash } from "./Shell";

// Tailwind classes with the brand tokens (tailwind.config.ts), as the rest of the dashboard.
const s = {
  panel: "mt-6 p-4 border border-solid border-line rounded-16 bg-card",
  title: "flex items-center gap-2 m-0 font-display text-[18px] font-bold",
  gallery: "grid gap-2.5 grid-cols-[repeat(auto-fill,minmax(108px,1fr))]",
  tile: "grid gap-1.5 p-1.5 border-2 border-solid border-line rounded-12 bg-panel text-text cursor-pointer text-left disabled:cursor-progress",
  on: "!border-lime",
  img: "w-full aspect-[9/16] object-contain rounded-8 bg-black",
  label: "flex items-center justify-between gap-1 text-[12px] text-muted",
  none: "grid place-items-center aspect-[9/16] text-[12px] text-muted text-center p-1.5",
  pending: "cursor-default border-dashed",
  row: "flex flex-wrap items-end gap-2.5",
  grow: "grow basis-[220px]",
  check: "flex items-start gap-2 text-[14px]",
  premium: "grid gap-2.5",
  legend: "flex items-center gap-1.5",
  confirm: "flex flex-wrap items-center gap-2.5 p-2.5 rounded-12 bg-panel",
};

// The clip's thumbnails in the editor: the gallery to choose from (free), the text on the chosen one (free), and,
// when the API lists it, the paid "Premium thumbnail" panel with its exact price shown before confirming.
export function ThumbnailPanel({ clip }: { clip: any }) {
  const { fail, reloadMe } = useDash();
  const [g, setG] = useState<Gallery | null>(null), [missing, setMissing] = useState(false);
  const [busy, setBusy] = useState(""), [said, setSaid] = useState("");
  const reload = useCallback(() => loadGallery(clip.id).then(setG).catch((e) => {
    if (e instanceof ApiError && (e.status === 404 || e.status === 405)) setMissing(true); else fail(e);
  }), [clip.id, fail]);
  useEffect(() => { reload(); }, [reload]);

  if (missing) return null;                       // this API has no thumbnail gallery yet
  if (!g) return <p className="muted small">Loading thumbnails…</p>;
  const chosen = g.thumbnails.find((t) => t.selected) || g.thumbnails[0];

  const run = async (label: string, act: () => Promise<Gallery>, done: string) => {
    setBusy(label); setSaid("");
    try { setG(await act()); setSaid(done); } catch (e) { fail(e); } finally { setBusy(""); }
  };

  return (
    <section className={`${s.panel} stack-s`} aria-labelledby="thumbs-title">
      <h2 id="thumbs-title" className={s.title}><Icon name="image" size={18} />Thumbnail</h2>
      <div className={s.gallery} role="radiogroup" aria-label="Choose the clip's thumbnail">
        {g.thumbnails.map((t) => (
          <button key={t.id} type="button" role="radio" aria-checked={t.selected} className={`${s.tile} ${t.selected ? s.on : ""}`}
            disabled={!!busy} onClick={() => !t.selected && run("choose", () => chooseThumb(clip.id, t.id), "Thumbnail chosen. Switching is free.")}>
            {t.url ? <img src={t.url} alt="" loading="lazy" className={s.img} /> : <span className={s.none}>No picture</span>}
            <span className={`${s.label} ${t.selected ? "text-lime" : ""}`}>{t.kind === "original" ? "Original · free" : styleName(g.premium, t.style)}{t.selected && <Icon name="check" size={14} />}</span>
          </button>
        ))}
        {g.pending.length > 0 && <div className={`${s.tile} ${s.pending}`} aria-live="polite"><span className={s.none}>Making a premium thumbnail…</span></div>}
      </div>
      {chosen && <TextControls key={chosen.id + String(chosen.text) + String(chosen.show_text)} hook={clip.hook} thumb={chosen} busy={!!busy}
        onSave={(body) => run("text", () => editThumb(clip.id, chosen.id, body), "Text updated. Free.")} />}
      {said && <p className="muted small" role="status">{said}</p>}
      {g.premium && <PremiumBox clip={clip} g={g} onDone={() => { reload(); reloadMe(); }} />}
    </section>
  );
}

function TextControls({ thumb, hook, busy, onSave }: { thumb: Gallery["thumbnails"][number]; hook?: string | null; busy: boolean;
  onSave: (b: { text?: string | null; show_text?: boolean }) => void }) {
  const [text, setText] = useState(thumb.text ?? ""), [show, setShow] = useState(thumb.show_text);
  if (!thumb.editable) return <p className="muted small">This thumbnail's text can't be changed (the clip was made before text editing).</p>;
  const changed = (text.trim() || null) !== (thumb.text || null) || show !== thumb.show_text;
  return (
    <div className={s.row}>
      <label className={s.grow}>Text on the thumbnail<input value={text} maxLength={80} placeholder={hook || "The clip's hook"} disabled={!show}
        onChange={(e) => setText(e.target.value)} /></label>
      <label className={s.check}><input type="checkbox" checked={show} onChange={(e) => setShow(e.target.checked)} />Show text</label>
      <button type="button" className="btn small ghost" disabled={busy || !changed} onClick={() => onSave({ text: text.trim() || null, show_text: show })}>Save text</button>
    </div>
  );
}

function PremiumBox({ clip, g, onDone }: { clip: any; g: Gallery; onDone: () => void }) {
  const premium = g.premium!;
  const [style, setStyle] = useState(premium.styles[0]?.id || ""), [notes, setNotes] = useState("");
  const [consent, setConsent] = useState(false), [confirming, setConfirming] = useState<string | null>(null);
  const [state, setState] = useState<{ working?: boolean; problem?: string; done?: boolean }>({});
  const body = useMemo(() => ({ style, ...(notes.trim() ? { instruction: notes.trim() } : {}) }), [style, notes]);
  const quote = useQuote(premiumQuotePath(clip.id), body);
  // Whether this clip still needs the likeness confirmation (asked once per clip); the quote route says so.
  const [needsConsent, setNeedsConsent] = useState(true);
  useEffect(() => {
    let on = true;
    api(premiumQuotePath(clip.id), { body: { style } }).then((r: any) => on && setNeedsConsent(r?.likeness_consent_required !== false)).catch(() => {});
    return () => { on = false; };
  }, [clip.id]);   // eslint-disable-line react-hooks/exhaustive-deps
  const price = quote.state === "ok" ? quote.credits : null;

  const start = async () => {
    if (price == null || !confirming) return;
    setState({ working: true });
    try {
      const job = await orderPremium(clip.id, confirming, { ...body, credits: price, likeness_consent: consent });
      setConfirming(null);
      onDone();
      await followJob(job.job_id, () => {}, 2000);
      setState({ done: true });
      setNeedsConsent(false);
    } catch (e) {
      setConfirming(null);
      setState({ problem: e instanceof Error ? e.message : "The premium thumbnail failed. Your credits were refunded." });
    } finally { onDone(); }
  };

  return (
    <fieldset className={`panels ${s.premium}`}>
      <legend className={s.legend}><Icon name="sparkle" size={16} />Premium thumbnail</legend>
      <p className="muted small">AI restyles this clip's frame. The streamer's face and the gameplay stay as they are; ClutchClips draws the text, so it's spelled exactly. Your free thumbnail is kept.</p>
      <div className={s.row}>
        <label>Style<select value={style} onChange={(e) => setStyle(e.target.value)}>
          {premium.styles.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}</select></label>
        <label className={s.grow}>Custom styling (optional)<input value={notes} maxLength={premium.instruction_max} placeholder="e.g. warm sunset tones"
          onChange={(e) => setNotes(e.target.value)} /></label>
      </div>
      {needsConsent && <label className={s.check}><input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />{premium.consent}</label>}
      <p aria-live="polite" className="small">
        {quote.state === "ok" ? <><b className="price">{creditWords(quote.credits)}</b> per thumbnail. {premium.note}</>
          : quote.state === "failed" ? <span className="warn">{quote.message}</span> : "Working out the price…"}</p>
      {state.problem && <p className="error" role="alert">{state.problem}</p>}
      {state.done && <p className="muted small" role="status">Done: the new thumbnail is in the gallery above. Choose it to use it.</p>}
      {!confirming ? (
        <button type="button" className="btn small primary" disabled={price == null || state.working || (needsConsent && !consent)}
          onClick={() => { setState({}); setConfirming(newOrderKey(clip.id)); }}>
          <Icon name="sparkle" size={16} />{price == null ? "Generate" : `Generate for ${creditWords(price)}`}</button>
      ) : (
        <div className={s.confirm} role="group" aria-label="Confirm the premium thumbnail">
          <p className="small basis-full m-0">This uses <b>{creditWords(price || 0)}</b> of your balance. If it fails, they're refunded in full.</p>
          <button type="button" className="btn small ghost" disabled={state.working} onClick={() => setConfirming(null)}>Back</button>
          <button type="button" className="btn small primary" disabled={state.working} onClick={start}>{state.working ? "Making it…" : `Confirm ${creditWords(price || 0)}`}</button>
        </div>
      )}
    </fieldset>
  );
}
