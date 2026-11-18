"use client";
// The project page's "make something" view for an uploaded video: Clip Maker on the full job-setup screen, and
// Reframe and Captions on their own short forms. The price for clipping is POST /v1/clips/quote for the exact
// request; without that route, the upload's own `credits_required`.
import { useState } from "react";
import { api } from "@/lib/api";
import { useQuote } from "@/lib/exporting";
import { useClipOptions } from "@/lib/options";
import { QUOTE, useRoutes } from "@/lib/routes";
import { useDash } from "../Shell";
import { Tabs } from "../Tabs";
import { RenderForm } from "../ToolPanel";
import { JobSetup, Price } from "./JobSetup";

type Make = "clips" | "reframe" | "captions";
const NAMES: [Make, string][] = [["clips", "Clip Maker"], ["reframe", "Reframe"], ["captions", "Captions"]];

export function MakeView({ upload, tool, template, onStarted, onBack, back }: { upload: any; tool?: string; template?: string; onStarted: (job: any) => void;
  onBack: () => void; back?: React.ReactNode }) {
  const { reloadMe, fail } = useDash();
  const listed = useClipOptions(), known = useRoutes();
  const [make, setMake] = useState<Make>(tool === "reframe" || tool === "captions" ? tool : "clips");
  const [options, setOptions] = useState<Record<string, unknown> | null>(null), [busy, setBusy] = useState(false);
  const body = options ? { upload_id: upload.upload_id, options } : null;
  const quote = useQuote(known?.quote ? QUOTE : null, known?.quote ? body : null);
  const price: Price = known === null || (known.quote && (quote.state === "none" || quote.state === "asking")) ? { state: "asking" }
    : quote.state === "ok" ? quote : quote.state === "failed" ? quote
    : upload.analyzed ? { state: "unknown", text: "This video is already paid for: you only use credits for the minutes rendered." }
    : { state: "ok", credits: upload.credits_required, note: "One credit per started minute of the video." };
  const tabs = <div className="flex flex-wrap items-center justify-between gap-3"><Tabs seg label="What to make" panel="make-panel" value={make} onChange={setMake} tabs={NAMES} />{back}</div>;

  async function create(opts: Record<string, unknown>) {
    setBusy(true);
    try { onStarted(await api("/v1/clips", { body: { upload_id: upload.upload_id, options: opts } })); await reloadMe(); }
    catch (e) { fail(e); } finally { setBusy(false); }
  }

  if (!listed) return <p className="muted">Loading the options…</p>;
  if (make === "clips") return (
    <div id="make-panel" role="tabpanel" aria-label="Clip Maker">
      <JobSetup listed={listed} template={template} busy={busy} price={price} onOptions={setOptions} onCreate={create} onRemove={onBack} header={tabs}
        source={{ title: upload.filename, duration: upload.duration_sec, height: upload.height, video: upload.source_url,
          thumb: upload.thumb_url || upload.clips?.find((c: any) => c.thumb_url)?.thumb_url }} />
    </div>
  );
  return (
    <div className="form-col">
      {tabs}
      <section id="make-panel" role="tabpanel" aria-label={make === "reframe" ? "Reframe" : "Captions"} className="panel">
        <RenderForm key={make} tool={make} upload={upload} listed={listed} onStarted={onStarted} />
      </section>
    </div>
  );
}
