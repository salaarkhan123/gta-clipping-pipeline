"use client";
import { useId } from "react";
import { useDash } from "./Shell";

// The credit price, then the button that spends it. `perMinute` tools (Clip Maker, Video Finder) charge for the
// whole video once; the others charge for the minutes they render.
// Inside a form, leave `onStart` out: the button submits the form.
export function StartRow({ upload, label, busy, perMinute, onStart }: { upload: any; label: string; busy: boolean; perMinute?: boolean; onStart?: () => void }) {
  const { me } = useDash();
  const price = useId();
  return (
    <div className="row start-row">
      <p className="muted" id={price}>{upload.analyzed
        ? "This video is already paid for. You only use credits for the minutes rendered."
        : perMinute ? `Uses ${upload.credits_required} credit${upload.credits_required === 1 ? "" : "s"} (one per minute of video).`
        : `Uses one credit per minute rendered, up to ${upload.credits_required}.`}</p>
      <button type={onStart ? "button" : "submit"} className="btn primary" disabled={busy || !me.email_verified} aria-describedby={price} onClick={onStart}>{busy ? "Starting…" : label}</button>
    </div>
  );
}
