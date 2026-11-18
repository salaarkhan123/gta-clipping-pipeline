"use client";
import { kindName, Mark, MARK_NAMES, Sort, View } from "./model";

const SEG = "min-h-[32px] cursor-pointer rounded-pill border-0 px-3 font-sans text-[13px] font-medium";
const CHIP = "inline-flex min-h-[32px] cursor-pointer items-center gap-[6px] rounded-pill border border-solid px-3 font-sans text-[13px] font-medium whitespace-nowrap";

// Sort (AI rating or where the moment is in the video), filter by kind (only the kinds the API gave these clips)
// and by your own marks.
export function ResultsBar({ view, onView, kinds, total }: { view: View; onView: (v: View) => void; kinds: { kind: string; count: number }[]; total: number }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div className="flex min-w-0 flex-wrap items-center gap-[6px]" role="group" aria-label="Filter by kind">
        <button type="button" aria-pressed={view.kind === null} onClick={() => onView({ ...view, kind: null })}
          className={`${CHIP} ${view.kind === null ? "border-btn bg-btn text-btn-ink" : "border-line-strong bg-transparent text-soft hover:text-text"}`}>
          All <span className="font-mono text-[11.5px] tabular-nums opacity-60">{total}</span></button>
        {kinds.map(({ kind, count }) => (
          <button key={kind} type="button" aria-pressed={view.kind === kind} onClick={() => onView({ ...view, kind: view.kind === kind ? null : kind })}
            className={`${CHIP} ${view.kind === kind ? "border-btn bg-btn text-btn-ink" : "border-line-strong bg-transparent text-soft hover:text-text"}`}>
            {kindName(kind)} <span className="font-mono text-[11.5px] tabular-nums opacity-60">{count}</span></button>))}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <label className="relative inline-flex items-center">
          <span className="sr-only">Show</span>
          <select value={view.mark} onChange={(e) => onView({ ...view, mark: e.target.value as Mark })}
            className="min-h-[34px] cursor-pointer appearance-none rounded-pill border border-solid border-line-strong bg-transparent py-0 pl-3 pr-8 font-sans text-[13px] text-text">
            {(Object.keys(MARK_NAMES) as Mark[]).map((m) => <option key={m} value={m} className="bg-card">{m === "all" ? "All clips" : MARK_NAMES[m]}</option>)}
          </select>
          <svg aria-hidden="true" viewBox="0 0 24 24" width="14" height="14" className="pointer-events-none absolute right-3 fill-none stroke-current stroke-2 text-fg-2"><path d="m7 10 5 5 5-5" /></svg>
        </label>
        <div role="radiogroup" aria-label="Sort" className="inline-flex rounded-pill bg-chip p-[3px]">
          {([["rating", "AI rating"], ["time", "Time"]] as [Sort, string][]).map(([s, label]) => (
            <button key={s} type="button" role="radio" aria-checked={view.sort === s} onClick={() => onView({ ...view, sort: s })}
              className={`${SEG} ${view.sort === s ? "bg-raised text-text shadow-card" : "bg-transparent text-fg-2 hover:text-text"}`}>{label}</button>))}
        </div>
      </div>
    </div>
  );
}
