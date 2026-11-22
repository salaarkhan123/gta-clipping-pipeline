"use client";
import { Icon } from "@/components/dash/Icon";
import { Dropdown, MenuItem, MenuLabel, MenuRule } from "@/components/ui/Dropdown";
import { kindName, Mark, MARK_NAMES, Sort, View } from "./model";

// [value, the row in the menu, the word on the button]
const SORTS: [Sort, string, string][] = [["rating", "AI rating", "AI rating"], ["duration", "Duration", "Duration"], ["time", "Time in the video", "Time"]];
const TRIGGER = "btn small ghost aria-expanded:bg-control-hover";

// One row above the clips. Left: grid or list (`children`) and how many are showing. Right: Select (the bulk bar),
// Filter (your own marks, and the kinds the API gave these clips) and Sort, each a dropdown.
export function ResultsBar({ view, onView, kinds, total, shown, selecting, onSelecting, children }: {
  view: View; onView: (v: View) => void; kinds: { kind: string; count: number }[]; total: number;
  shown?: number; selecting?: boolean; onSelecting?: (on: boolean) => void; children?: React.ReactNode;
}) {
  const filters = (view.kind ? 1 : 0) + (view.mark !== "all" ? 1 : 0);
  const showing = shown ?? total;
  return (
    <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2">
      <div className="flex min-w-0 items-center gap-3">
        {children}
        <p className="m-0 text-[14px] tabular-nums text-fg-2" aria-live="polite">
          {showing === total ? `${total} clip${total === 1 ? "" : "s"}` : `${showing} of ${total} clips`}</p>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {onSelecting && <button type="button" className="btn small ghost" aria-pressed={!!selecting} onClick={() => onSelecting(!selecting)}>
          <Icon name="check" size={15} />Select</button>}
        <Dropdown label="Filter clips" align="end" panelClass="w-[220px] rounded-[16px] p-2"
          trigger={(t) => <button {...t} type="button" className={TRIGGER}><Icon name="sliders" size={15} />Filter
            {filters > 0 && <span className="grid h-[18px] min-w-[18px] place-items-center rounded-pill bg-btn px-1 text-[11px] font-medium tabular-nums text-btn-ink">{filters}</span>}</button>}>
          {(close) => <>
            <MenuLabel>Show</MenuLabel>
            {(Object.keys(MARK_NAMES) as Mark[]).map((m) => <MenuItem key={m} checked={view.mark === m} onSelect={() => { onView({ ...view, mark: m }); close(); }}>
              {m === "all" ? "All clips" : MARK_NAMES[m]}</MenuItem>)}
            {kinds.length > 0 && <>
              <MenuRule />
              <MenuLabel>Kind</MenuLabel>
              <MenuItem checked={view.kind === null} onSelect={() => { onView({ ...view, kind: null }); close(); }}>Every kind</MenuItem>
              {kinds.map(({ kind, count }) => <MenuItem key={kind} checked={view.kind === kind} onSelect={() => { onView({ ...view, kind }); close(); }}
                after={<span className="text-[12px] tabular-nums text-fg-2">{count}</span>}>{kindName(kind)}</MenuItem>)}
            </>}
          </>}
        </Dropdown>
        <Dropdown label="Sort clips" align="end" panelClass="w-[220px] rounded-[16px] p-2"
          trigger={(t) => <button {...t} type="button" className={TRIGGER}>
            <span className="text-fg-2 narrow:hidden">Sort</span>{SORTS.find(([s]) => s === view.sort)?.[2]}
            <Icon name="chevron" size={15} className="text-fg-2" /></button>}>
          {(close) => SORTS.map(([s, label]) => <MenuItem key={s} checked={view.sort === s} onSelect={() => { onView({ ...view, sort: s }); close(); }}>{label}</MenuItem>)}
        </Dropdown>
      </div>
    </div>
  );
}
