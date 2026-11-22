"use client";
import { kindName, Mark, MARK_NAMES, Sort, View } from "./model";

const SEG = "h-8 cursor-pointer rounded-pill border-0 px-4 font-sans text-[13px] font-medium transition-colors duration-base";
const CHIP = "inline-flex h-8 cursor-pointer items-center gap-[6px] rounded-pill border-0 px-4 font-sans text-[13px] font-medium whitespace-nowrap transition-colors duration-base";

// Sort (AI rating or where the moment is in the video), filter by kind (only the kinds the API gave these clips)
// and by your own marks.
export function ResultsBar({ view, onView, kinds, total, children }: {
  view: View; onView: (v: View) => void; kinds: { kind: string; count: number }[]; total: number; children?: React.ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div className="flex min-w-0 flex-wrap items-center gap-[6px] narrow:-mx-4 narrow:w-[calc(100%+32px)] narrow:flex-nowrap narrow:overflow-x-auto narrow:px-4 narrow:pb-1 narrow:[scrollbar-width:none]" role="group" aria-label="Filter by kind">
        <button type="button" aria-pressed={view.kind === null} onClick={() => onView({ ...view, kind: null })}
          className={`${CHIP} ${view.kind === null ? "bg-btn text-btn-ink" : "bg-control text-text hover:bg-control-hover"}`}>
          All <span className="font-mono text-[11.5px] tabular-nums opacity-60">{total}</span></button>
        {kinds.map(({ kind, count }) => (
          <button key={kind} type="button" aria-pressed={view.kind === kind} onClick={() => onView({ ...view, kind: view.kind === kind ? null : kind })}
            className={`${CHIP} ${view.kind === kind ? "bg-btn text-btn-ink" : "bg-control text-text hover:bg-control-hover"}`}>
            {kindName(kind)} <span className="font-mono text-[11.5px] tabular-nums opacity-60">{count}</span></button>))}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <label className="relative inline-flex items-center">
          <span className="sr-only">Show</span>
          <select value={view.mark} onChange={(e) => onView({ ...view, mark: e.target.value as Mark })}
            className="h-8 cursor-pointer appearance-none rounded-pill border-0 bg-control py-0 pl-4 pr-8 font-sans text-[13px] text-text">
            {(Object.keys(MARK_NAMES) as Mark[]).map((m) => <option key={m} value={m} className="bg-card">{m === "all" ? "All clips" : MARK_NAMES[m]}</option>)}
          </select>
          <svg aria-hidden="true" viewBox="0 0 24 24" width="14" height="14" className="pointer-events-none absolute right-3 fill-none stroke-current stroke-2 text-fg-2"><path d="m7 10 5 5 5-5" /></svg>
        </label>
        <div role="radiogroup" aria-label="Sort" className="inline-flex gap-2">
          {([["rating", "AI rating"], ["duration", "Duration"], ["time", "Time"]] as [Sort, string][]).map(([s, label]) => (
            <button key={s} type="button" role="radio" aria-checked={view.sort === s} onClick={() => onView({ ...view, sort: s })}
              className={`${SEG} ${view.sort === s ? "bg-btn text-btn-ink" : "bg-control text-text hover:bg-control-hover"}`}>{label}</button>))}
        </div>
        {children}
      </div>
    </div>
  );
}
