"use client";
import { useCallback, useEffect, useState } from "react";
import { ClipCard, ClipFilter, ClipSort, ClipToolbar } from "@/components/dash/ClipCard";
import { useDash } from "@/components/dash/Shell";
import { api } from "@/lib/api";

const PAGE = 24;

// Library: every clip on the account, newest first.
export default function Library() {
  const { fail } = useDash();
  const [clips, setClips] = useState<any[] | null>(null), [total, setTotal] = useState(0), [busy, setBusy] = useState(false);
  const [sort, setSort] = useState<ClipSort>("newest"), [filter, setFilter] = useState<ClipFilter>("all");

  const more = useCallback(async (offset: number) => {
    setBusy(true);
    try {
      const r = await api(`/v1/clips?limit=${PAGE}&offset=${offset}&sort=${sort}&filter=${filter}`);
      setTotal(r.total);
      setClips((list) => (offset ? [...(list || []), ...r.clips] : r.clips));
    } catch (e) { fail(e); } finally { setBusy(false); }
  }, [fail, sort, filter]);
  useEffect(() => { more(0); }, [more]);

  return (
    <>
      <h1 className="dash-title">Library</h1>
      <ClipToolbar sort={sort} filter={filter} sorts={["newest", "score", "time"]} onSort={setSort} onFilter={setFilter} />
      {clips === null ? <p className="muted">Loading your clips…</p>
        : !clips.length ? <p className="muted">{filter === "all" ? "No clips yet. Open a project and make some." : "No clips match this filter."}</p>
        : <>
            <p className="muted">{total} clip{total === 1 ? "" : "s"}. Clips are kept for 7 days.</p>
            <div className="clips">
              {clips.map((c) => <ClipCard key={c.id} clip={c} project={{ id: c.upload_id, name: c.filename }}
                onChange={(n) => setClips((list) => list!.map((x) => (x.id === n.id ? n : x)))} />)}
            </div>
            {clips.length < total && <button className="btn ghost" disabled={busy} onClick={() => more(clips.length)}>{busy ? "Loading…" : "Show more"}</button>}
          </>}
    </>
  );
}
