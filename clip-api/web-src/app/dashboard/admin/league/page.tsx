"use client";
// Admin: Creators League. Competitions and prizes, entry review, view counts, winners and the audit log.
// The dashboard frame (Shell) reads GET /v1/me before any page draws; an account without `is_admin` sees "Admins
// only" and this page asks the API for nothing. The admin routes check is_admin themselves (app/deps.py).
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useDash } from "@/components/dash/Shell";
import { BackTitle, PAGE_HEAD } from "@/components/dash/ui";
import { api } from "@/lib/api";
import { COMPETITION_RULES, CompetitionAction, dollars, ENTRY_RULES, EntryAction, moment, ordinal, PLATFORM_LABEL, Platform, Prize, safeVideoUrl } from "@/lib/league";

type Counts = Record<"pending" | "approved" | "rejected" | "disqualified", number>;
type Competition = { id: string; slug: string; name: string; starts_at: string; ends_at: string; status: string; phase: string; prizes: Prize[];
  rules_version: string; cash_prizes_enabled: boolean; cash_prizes_approved: boolean; entries: Counts };
type Observation = { views: number; source: string; verified: boolean; observed_at: string; observed_by: string };
type Entry = { id: string; status: string; status_reason: string | null; flagged: boolean; flag_reason: string | null; platform: Platform; video_url: string;
  game: string | null; thumb_url: string | null; username: string | null; email: string | null; submitted_at: string; rank: number | null; views: number | null;
  final_place: number | null; prize_status: string | null; observations: Observation[]; snapshot: Record<string, unknown> };
type Winner = Entry & { place: number; state: "provisional" | "final"; prize: Prize | null };
type Event = { id: number; action: string; entity_kind: string; entity_id: string; actor_id: string; before: unknown; after: unknown; reason: string | null; created_at: string };

const INPUT = "h-10 w-full rounded-12 border border-solid border-transparent bg-control px-3 font-sans text-[14px] text-text placeholder:text-fg-3 focus:border-line-strong focus:outline-none";
const LABEL = "grid gap-1.5 text-[13px] font-medium text-text";
const MOVE_LABEL: Record<CompetitionAction, string> = { open: "Open to the public", close: "Close entries", reopen: "Reopen entries", finalize: "Make results final" };
const REVIEW_LABEL: Record<EntryAction, string> = { approve: "Approve", reject: "Reject", disqualify: "Disqualify" };
const local = (iso: string) => { const d = new Date(iso); return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16); };

export default function AdminLeaguePage() {
  const { me } = useDash();
  if (!me.is_admin) return (
    <section className="panel" aria-labelledby="admins-only">
      <BackTitle title="Admins only" id="admins-only" crumbs={[{ label: "Home", href: "/dashboard/" }, { label: "Admins only" }]} />
      <p className="muted">This page is for ClutchClips admins. <Link className="underline" href="/dashboard/">Back to Home</Link></p>
    </section>
  );
  return <Admin />;
}

function Admin() {
  const [list, setList] = useState<Competition[] | null>(null), [slug, setSlug] = useState(""), [problem, setProblem] = useState("");
  const load = useCallback(() => api("/v1/admin/league/competitions").then((r) => { setList(r.competitions); setSlug((s) => s || r.competitions[0]?.slug || ""); })
    .catch((e) => setProblem(e.message)), []);
  useEffect(() => { load(); }, [load]);
  const current = list?.find((c) => c.slug === slug) || null;
  return (
    <div className="stack">
      <div className={PAGE_HEAD}><BackTitle title="Admin: Creators League" crumbs={[{ label: "Home", href: "/dashboard/" }, { label: "Admin: Creators League" }]} /></div>
      {problem && <p className="error" role="alert">{problem}</p>}
      {list === null ? <p className="muted">Loading…</p> : <>
        <section className="panel" aria-labelledby="comps-title">
          <h2 id="comps-title" className="text-[18px] font-semibold">Competitions</h2>
          {list.length === 0 ? <p className="muted">No competition yet. Create the first one below. It starts as a draft only admins can see.</p>
            : <div className="flex flex-wrap gap-2" role="tablist" aria-label="Competitions">
              {list.map((c) => <button key={c.slug} type="button" role="tab" aria-selected={c.slug === slug} onClick={() => setSlug(c.slug)}
                className={`btn small ${c.slug === slug ? "primary" : "ghost"}`}>{c.name} · {c.status}</button>)}
            </div>}
          <NewCompetition onMade={(s) => { setSlug(s); load(); }} />
        </section>
        {current && <Manage key={current.slug} c={current} reload={load} />}
      </>}
    </div>
  );
}

function NewCompetition({ onMade }: { onMade: (slug: string) => void }) {
  const [name, setName] = useState(""), [slug, setSlug] = useState(""), [starts, setStarts] = useState(""), [ends, setEnds] = useState("");
  const [problem, setProblem] = useState(""), [busy, setBusy] = useState(false);
  const make = async (e: React.FormEvent) => {
    e.preventDefault(); setBusy(true); setProblem("");
    try {
      await api("/v1/admin/league/competitions", { body: { name, slug, starts_at: new Date(starts).toISOString(), ends_at: new Date(ends).toISOString(), prizes: [] } });
      setName(""); setSlug(""); onMade(slug);
    } catch (err: any) { setProblem(err.message); } finally { setBusy(false); }
  };
  return (
    <details className="rounded-16 bg-control/40 p-4">
      <summary className="cursor-pointer text-[14px] font-medium">New competition</summary>
      <form className="mt-4 grid grid-cols-4 items-end gap-3 narrow:grid-cols-1" onSubmit={make}>
        <label className={LABEL}>Name<input className={INPUT} value={name} onChange={(e) => setName(e.target.value)} required minLength={3} maxLength={80} placeholder="December 2026" /></label>
        <label className={LABEL}>Slug<input className={INPUT} value={slug} onChange={(e) => setSlug(e.target.value.toLowerCase())} required pattern="[a-z0-9][a-z0-9-]{1,38}[a-z0-9]" placeholder="2026-12" /></label>
        <label className={LABEL}>Starts<input className={INPUT} type="datetime-local" value={starts} onChange={(e) => setStarts(e.target.value)} required /></label>
        <label className={LABEL}>Ends<input className={INPUT} type="datetime-local" value={ends} onChange={(e) => setEnds(e.target.value)} required /></label>
        {problem && <p className="error col-span-full" role="alert">{problem}</p>}
        <button type="submit" className="btn small primary justify-self-start" disabled={busy}>Create draft</button>
      </form>
    </details>
  );
}

function Manage({ c, reload }: { c: Competition; reload: () => void }) {
  const [entries, setEntries] = useState<Entry[] | null>(null), [winners, setWinners] = useState<Winner[]>([]), [events, setEvents] = useState<Event[]>([]);
  const [problem, setProblem] = useState(""), [filter, setFilter] = useState("");
  const load = useCallback(() => {
    const q = filter ? `?status=${filter}` : "";
    api(`/v1/admin/league/competitions/${c.slug}/entries` + q).then((r) => setEntries(r.entries)).catch((e) => setProblem(e.message));
    api(`/v1/admin/league/competitions/${c.slug}/winners`).then((r) => setWinners(r.winners)).catch(() => {});
    api(`/v1/admin/league/events?competition=${c.slug}&limit=50`).then((r) => setEvents(r.events)).catch(() => {});
  }, [c.slug, filter]);
  useEffect(load, [load]);
  const act = async (path: string, body: unknown, method = "POST") => {
    setProblem("");
    try { await api(path, { method, body }); load(); reload(); } catch (err: any) { setProblem(err.message); }
  };
  const moves = (Object.keys(COMPETITION_RULES) as CompetitionAction[]).filter((a) => COMPETITION_RULES[a].includes(c.status));
  return (
    <>
      {problem && <p className="error" role="alert">{problem}</p>}
      <section className="panel" aria-labelledby="comp-title">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div><h2 id="comp-title" className="text-[18px] font-semibold">{c.name}</h2>
            <p className="muted text-[14px]">{moment(c.starts_at)} to {moment(c.ends_at)} · status {c.status} · rules {c.rules_version}</p></div>
          <div className="flex flex-wrap gap-2">
            {moves.map((a) => <button key={a} type="button" className="btn small ghost" onClick={() => { if (window.confirm(`${MOVE_LABEL[a]}: ${c.name}?`)) act(`/v1/admin/league/competitions/${c.slug}/status`, { action: a }); }}>{MOVE_LABEL[a]}</button>)}
            {c.status === "draft" && <button type="button" className="btn small ghost" onClick={() => { if (window.confirm(`Delete the draft ${c.name}?`)) act(`/v1/admin/league/competitions/${c.slug}`, undefined, "DELETE"); }}>Delete draft</button>}
          </div>
        </div>
        <p className="muted text-[14px]">Entries: {c.entries.pending} pending, {c.entries.approved} approved, {c.entries.rejected} rejected, {c.entries.disqualified} disqualified.</p>
        {c.status !== "finalized" && <Settings c={c} save={(body) => act(`/v1/admin/league/competitions/${c.slug}`, body, "PATCH")} />}
      </section>

      <section className="panel" aria-labelledby="winners-title">
        <h2 id="winners-title" className="text-[18px] font-semibold">Winners</h2>
        <p className="muted text-[14px]">The top three of the ranking. A place is provisional until you approve it here, first place first, after entries are closed. Nothing is paid by this system: record each prize after you send it yourself.</p>
        {winners.length === 0 ? <p className="muted">No approved entries yet.</p> : (
          <div className="table-wrap"><table className="ledger">
            <thead><tr><th scope="col">Place</th><th scope="col">Creator</th><th scope="col">Views</th><th scope="col">Prize</th><th scope="col">State</th><th scope="col">Action</th></tr></thead>
            <tbody>{winners.map((w) => (
              <tr key={w.id}>
                <td>{ordinal(w.place)}</td><td>{w.username}<br /><span className="muted text-[12.5px]">{w.email}</span></td>
                <td className="tabular-nums">{w.views === null ? "No count" : w.views.toLocaleString("en-US")}</td>
                <td>{w.prize ? dollars(w.prize.amount_cents) : "None set"}{w.prize_status ? ` · ${w.prize_status}` : ""}</td>
                <td>{w.state === "final" ? "Approved" : "Provisional"}</td>
                <td><span className="flex flex-wrap justify-end gap-2">
                  {w.state === "provisional" && c.status === "closed" && <button type="button" className="btn small primary" onClick={() => { if (window.confirm(`Approve ${w.username} as ${ordinal(w.place)} place? This cannot be undone.`)) act(`/v1/admin/league/entries/${w.id}/winner`, { place: w.place }); }}>Approve winner</button>}
                  {w.prize_status === "pending" && (["sent", "forfeited"] as const).map((s) => <button key={s} type="button" className="btn small ghost" onClick={() => { const note = window.prompt(s === "sent" ? "How was the prize sent? (method and reference)" : "Why was the prize forfeited?"); if (note) act(`/v1/admin/league/entries/${w.id}/prize`, { status: s, note }); }}>Mark {s}</button>)}
                </span></td>
              </tr>))}</tbody>
          </table></div>)}
      </section>

      <section className="panel" aria-labelledby="entries-title">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 id="entries-title" className="text-[18px] font-semibold">Entries</h2>
          <label className="flex items-center gap-2 text-[14px]">Show
            <select className="min-w-[10rem]" value={filter} onChange={(e) => setFilter(e.target.value)}>
              <option value="">All</option>{["pending", "approved", "rejected", "disqualified"].map((s) => <option key={s} value={s}>{s}</option>)}</select></label>
        </div>
        {entries === null ? <p className="muted">Loading…</p> : entries.length === 0 ? <p className="muted">No entries{filter ? " with this status" : " yet"}.</p>
          : <ul className="m-0 grid list-none gap-3 p-0">{entries.map((e) => <EntryRow key={e.id} e={e} act={act} final={c.status === "finalized"} />)}</ul>}
      </section>

      <section className="panel" aria-labelledby="audit-title">
        <h2 id="audit-title" className="text-[18px] font-semibold">Audit log</h2>
        {events.length === 0 ? <p className="muted">Nothing recorded yet.</p> : (
          <ol className="m-0 grid max-h-[480px] list-none gap-0 overflow-y-auto rounded-16 border border-solid border-line-soft p-0" aria-label="Audit log, newest first">
            {events.map((ev) => (
              <li key={ev.id} className="grid gap-1 border-0 border-b border-solid border-line-soft px-4 py-3 text-[13.5px] last:border-b-0">
                <span className="flex flex-wrap gap-x-4 gap-y-1"><strong>{ev.action}</strong><span className="muted">{moment(ev.created_at)}</span>
                  <span className="muted font-mono text-[12px]">{ev.entity_kind} {ev.entity_id}</span><span className="muted font-mono text-[12px]">by {ev.actor_id}</span></span>
                {(ev.before !== null || ev.after !== null) && <span className="font-mono text-[12px] text-fg-2 [overflow-wrap:anywhere]">{ev.before ? `${JSON.stringify(ev.before)} → ` : ""}{ev.after ? JSON.stringify(ev.after) : ""}</span>}
                {ev.reason && <span><span className="muted">Reason: </span>{ev.reason}</span>}
              </li>))}
          </ol>)}
      </section>
    </>
  );
}

function Settings({ c, save }: { c: Competition; save: (body: unknown) => void }) {
  const amount = (place: number) => String((c.prizes.find((p) => p.place === place)?.amount_cents || 0) / 100);
  const [name, setName] = useState(c.name), [starts, setStarts] = useState(local(c.starts_at)), [ends, setEnds] = useState(local(c.ends_at));
  const [prizes, setPrizes] = useState([amount(1), amount(2), amount(3)]), [cash, setCash] = useState(c.cash_prizes_enabled);
  return (
    <form className="grid gap-4" onSubmit={(e) => { e.preventDefault(); save({ name, starts_at: new Date(starts).toISOString(), ends_at: new Date(ends).toISOString(), cash_prizes_enabled: cash,
      prizes: prizes.map((p, i) => ({ place: i + 1, amount_cents: Math.round(Number(p || 0) * 100) })).filter((p) => p.amount_cents > 0) }); }}>
      <div className="grid grid-cols-3 gap-3 narrow:grid-cols-1">
        <label className={LABEL}>Name<input className={INPUT} value={name} onChange={(e) => setName(e.target.value)} required minLength={3} maxLength={80} /></label>
        <label className={LABEL}>Starts<input className={INPUT} type="datetime-local" value={starts} onChange={(e) => setStarts(e.target.value)} required /></label>
        <label className={LABEL}>Ends<input className={INPUT} type="datetime-local" value={ends} onChange={(e) => setEnds(e.target.value)} required /></label>
      </div>
      <div className="grid grid-cols-3 gap-3 narrow:grid-cols-1">
        {prizes.map((p, i) => <label key={i} className={LABEL}>{ordinal(i + 1)} prize (USD)
          <input className={INPUT} type="number" min={0} step="1" value={p} onChange={(e) => setPrizes(prizes.map((x, j) => (j === i ? e.target.value : x)))} /></label>)}
      </div>
      <label className="flex items-start gap-3 text-[14px] font-normal"><input type="checkbox" className="mt-[3px]" checked={cash} disabled={!c.cash_prizes_approved} onChange={(e) => setCash(e.target.checked)} />
        <span>Show cash prizes on the public page.{!c.cash_prizes_approved && <span className="muted"> Locked: the server setting LEAGUE_CASH_PRIZES_APPROVED is off. Turn it on only after the official rules have been reviewed by a lawyer. Until then the public page shows no amounts.</span>}</span></label>
      <button type="submit" className="btn small ghost justify-self-start">Save settings</button>
    </form>
  );
}

function EntryRow({ e, act, final }: { e: Entry; act: (path: string, body: unknown) => void; final: boolean }) {
  const [reason, setReason] = useState(""), [count, setCount] = useState("");
  const url = safeVideoUrl(e.video_url);
  const reviews = (Object.keys(ENTRY_RULES) as EntryAction[]).filter((a) => ENTRY_RULES[a].includes(e.status));
  const review = (action: string) => act(`/v1/admin/league/entries/${e.id}/review`, { action, reason: reason.trim() || null });
  return (
    <li className={`grid grid-cols-[56px_1fr] gap-4 rounded-16 border border-solid p-4 ${e.flagged ? "border-warn" : "border-line-soft"}`}>
      <span className="relative block aspect-[9/16] overflow-hidden rounded-8 bg-control">{e.thumb_url && <img src={e.thumb_url} alt="" className="absolute inset-0 h-full w-full object-cover" />}</span>
      <div className="grid min-w-0 gap-3">
        <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1 text-[14px]">
          <strong>{e.username || "No username"}</strong><span className="muted [overflow-wrap:anywhere]">{e.email}</span>
          <span>{e.status}{e.rank ? ` · #${e.rank}` : ""}{e.final_place ? ` · ${ordinal(e.final_place)} place approved` : ""}</span>
          {e.flagged && <span className="text-warn">Flagged: {e.flag_reason}</span>}
        </div>
        <p className="muted m-0 flex flex-wrap gap-x-4 gap-y-1 text-[13px]">
          <span>{PLATFORM_LABEL[e.platform]}</span><span>{e.game || "No game"}</span><span>Submitted {moment(e.submitted_at)}</span>
          {url ? <a href={url} target="_blank" rel="noopener noreferrer nofollow" className="underline">Open the video and check the description</a> : <span>Link not shown: {e.video_url}</span>}
        </p>
        {e.status_reason && <p className="m-0 text-[13px]"><span className="muted">Reason given: </span>{e.status_reason}</p>}
        <p className="muted m-0 text-[13px]">Views (unverified, read by hand): {e.observations.length === 0 ? "none recorded" : e.observations.map((o) => `${o.views.toLocaleString("en-US")} at ${moment(o.observed_at)}`).join(" · ")}</p>
        {!final && <div className="grid grid-cols-[1fr_auto] items-end gap-3 narrow:grid-cols-1">
          <label className={LABEL}>Reason (the creator sees it for reject and disqualify; a flag stays private)
            <input className={INPUT} value={reason} onChange={(ev) => setReason(ev.target.value)} maxLength={500} /></label>
          <span className="flex flex-wrap gap-2">
            {reviews.map((a) => <button key={a} type="button" className={`btn small ${a === "approve" ? "primary" : "ghost"}`} onClick={() => review(a)}>{REVIEW_LABEL[a]}</button>)}
            <button type="button" className="btn small ghost" onClick={() => review(e.flagged ? "unflag" : "flag")}>{e.flagged ? "Remove flag" : "Flag"}</button>
          </span>
        </div>}
        {!final && e.status === "approved" && <form className="flex flex-wrap items-end gap-3" onSubmit={(ev) => { ev.preventDefault(); act(`/v1/admin/league/entries/${e.id}/observations`, { views: Number(count), source: "public_page" }); setCount(""); }}>
          <label className={LABEL}>Views on the public page now<input className={`${INPUT} w-[200px]`} type="number" min={0} step={1} value={count} onChange={(ev) => setCount(ev.target.value)} required /></label>
          <button type="submit" className="btn small ghost">Record views</button>
        </form>}
      </div>
    </li>
  );
}
