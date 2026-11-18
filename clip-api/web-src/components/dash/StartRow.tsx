"use client";
import { useId } from "react";
import { creditWords, Quote } from "@/lib/exporting";
import { useDash } from "./Shell";

// The credit price, then the button that spends it. `perMinute` tools (Clip Maker, Video Finder) charge for the
// whole video once; the others charge for the minutes they render.
// Inside a form, leave `onStart` out: the button submits the form.
// `quote` (when the API has a quote route) replaces the wording with the exact reservation, and the button waits for it.
export function StartRow({ upload, label, busy, perMinute, onStart, quote }: { upload: any; label: string; busy: boolean; perMinute?: boolean; onStart?: () => void; quote?: Quote }) {
  const { me } = useDash();
  const price = useId();
  const priced = quote && quote.state !== "none";
  return (
    <div className="row start-row">
      <p className="muted" id={price} aria-live="polite">{priced ? <QuoteLine quote={quote} /> : upload.analyzed
        ? "This video is already paid for. You only use credits for the minutes rendered."
        : perMinute ? `Uses ${upload.credits_required} credit${upload.credits_required === 1 ? "" : "s"} (one per minute of video).`
        : `Uses one credit per minute rendered, up to ${upload.credits_required}.`}</p>
      <button type={onStart ? "button" : "submit"} className="btn primary" disabled={busy || !me.email_verified || (priced && quote.state !== "ok")} aria-describedby={price} onClick={onStart}>{busy ? "Starting…" : label}</button>
    </div>
  );
}

export function QuoteLine({ quote, what = "This run" }: { quote: Quote; what?: string }) {
  if (quote.state === "asking") return <>Working out the price…</>;
  if (quote.state === "failed") return <span className="warn">No price yet: {quote.message}</span>;
  if (quote.state !== "ok") return null;
  return <><b className="price">{what} reserves {creditWords(quote.credits)}.</b> {quote.note || "The exact amount from the API; nothing is reserved until you start."}</>;
}
