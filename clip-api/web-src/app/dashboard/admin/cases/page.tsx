"use client";
// Admin: copyright and likeness cases. The dashboard frame (Shell) reads GET /v1/me before any page draws; an
// account without `is_admin` sees "Admins only" and this page asks the API for no case data. The admin routes check
// is_admin themselves (app/deps.py admin_principal), so this gate only spares a 403.
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";
import { useDash } from "@/components/dash/Shell";
import { PAGE_HEAD, PAGE_TITLE } from "@/components/dash/ui";
import { DecisionBody, DecisionDialog } from "@/components/trust/DecisionDialog";
import { LINK } from "@/components/trust/Field";
import { api } from "@/lib/api";
import { focusSoon, KIND_LABEL, STATUS_LABEL, STATUSES, TARGET_LABEL, when } from "@/lib/trust";

type Action = "review" | "request_info" | "forward_notice" | "disable" | "remove" | "reject" | "withdraw" | "restore"
  | "delete_content" | "terminate" | "note" | "close";
// The statuses each decision may be taken from: RULES in app/trust_decisions.py, one line per action
// (tests/test_case_screens.py checks the two match). The API refuses anything else with a 409.
const RULES: Record<Action, string[]> = {
  review: ["received", "info_requested"],
  request_info: ["received", "in_review", "info_requested"],
  forward_notice: ["received", "in_review", "info_requested", "disabled", "removed"],
  disable: ["received", "in_review", "info_requested"],
  remove: ["received", "in_review", "info_requested", "disabled"],
  reject: ["received", "in_review", "info_requested", "disabled"],
  withdraw: ["received", "in_review", "info_requested", "disabled", "removed", "counter_noticed"],
  restore: ["disabled", "removed", "counter_noticed"],
  delete_content: ["removed"],
  terminate: ["received", "in_review", "info_requested", "disabled", "removed", "counter_noticed"],
  note: ["received", "in_review", "info_requested", "disabled", "removed", "rejected", "withdrawn", "restored", "counter_noticed", "closed"],
  close: ["removed", "rejected", "withdrawn", "restored"],
};
const ACTIONS = Object.keys(RULES) as Action[];

type Target = { kind: string; id: string; state: string; account_id: string; account_email: string | null };
type Event = { id: number; actor_kind: string; actor_id: string | null; action: string; note: string | null; data: Record<string, unknown> | null; created_at: string };
type Case = { reference: string; kind: string; status: string; claimant_name: string; claimant_organization: string | null;
  targets: number | Target[]; urls: number; created_at: string; updated_at: string };
type FullCase = Omit<Case, "targets"> & { targets: Target[]; events: Event[]; work: string; reported_urls: string[]; details: string | null;
  signature: string; ip_hash: string; claimant: { name: string; email: string; organization: string | null; address: string | null; phone: string | null; relationship: string } };

const owners = (c: FullCase) => Array.from(new Map(c.targets.map((t) => [t.account_id, { id: t.account_id, email: t.account_email }])).values());
const who = (o: { id: string; email: string | null }) => o.email || o.id;
const list = (xs: string[]) => (xs.length ? xs.join(", ") : "no account");

// What each decision does, as the dialog says it. `danger` is the second confirm of a destructive decision.
const MEANING: Record<Action, { label: string; what: string; message?: "required" | "optional"; danger?: (c: FullCase, account: string) => string }> = {
  review: { label: "Start review", what: "Marks the case as in review. Changes no content and sends no email." },
  request_info: { label: "Ask for information", message: "required", what: "Emails your message to the claimant and waits for their answer. Changes no content." },
  forward_notice: { label: "Forward the notice", what: "Emails the notice to every account holder whose content is reported, with the claimant's name or organisation and the work, never their contact details. Removes nothing." },
  disable: { label: "Disable the content", what: "Hides the reported content and keeps its files, so Restore or Reject can bring it back. Emails the account holders. Links handed out before keep working until they expire." },
  remove: { label: "Remove (verified)", what: "The verified decision: the content stays hidden and each account holder gets one strike under the repeat-infringer policy.",
    danger: (c) => `This keeps the reported content hidden and gives one strike to each account in this case (${list(owners(c).map(who))}). An account that reaches the repeat-infringer limit is suspended at once.` },
  reject: { label: "Reject", message: "optional", what: "Closes the report without action and brings back anything it disabled. Emails the claimant (with your message, if any) and the account holders." },
  withdraw: { label: "Mark as withdrawn", what: "The claimant withdrew. Brings back anything disabled and cancels this case's strikes." },
  restore: { label: "Restore the content", what: "Brings the content back where its files still exist, and cancels this case's strikes. Emails the claimant and the account holders." },
  delete_content: { label: "Delete the files", what: "Removes the stored files of the removed content.",
    danger: (c) => `This permanently deletes the stored files of ${c.targets.filter((t) => t.state === "disabled").length} hidden item(s) in this case. They cannot be restored afterwards.` },
  terminate: { label: "Terminate an account", what: "Suspends one account holder in this case at once, for a serious violation. They are emailed.",
    danger: (c, account) => `This suspends ${who(owners(c).find((o) => o.id === account) || { id: account, email: null })} now. A suspended account cannot sign in or use the API.` },
  note: { label: "Add a note", what: "Adds a note to the case history. Changes nothing else." },
  close: { label: "Close the case", what: "Closes the case. Changes no content." },
};

// useSearchParams needs a Suspense boundary in a static export.
export default function AdminCasesPage() { return <Suspense><Gate /></Suspense>; }

function Gate() {
  const { me } = useDash();
  const ref = (useSearchParams().get("ref") || "").trim().toUpperCase();
  if (!me.is_admin) return (
    <section className="panel" aria-labelledby="admins-only">
      <h1 id="admins-only" className={PAGE_TITLE}>Admins only</h1>
      <p className="muted">This page is for ClutchClips admins. <Link className={LINK} href="/dashboard/">Back to Home</Link></p>
    </section>
  );
  return ref ? <CaseView reference={ref} /> : <CaseList />;
}

const PAGE = 25;
const SELECT = "min-w-[11rem]";

function CaseList() {
  const [status, setStatus] = useState(""), [kind, setKind] = useState(""), [offset, setOffset] = useState(0);
  const [data, setData] = useState<{ total: number; cases: Case[] } | null>(null), [problem, setProblem] = useState("");
  useEffect(() => {
    const q = new URLSearchParams({ limit: String(PAGE), offset: String(offset) });
    if (status) q.set("status", status);
    if (kind) q.set("kind", kind);
    setData(null); setProblem("");
    api(`/v1/admin/trust/cases?${q}`).then(setData).catch((e) => setProblem(e.message));
  }, [status, kind, offset]);

  return (
    <div className="stack">
      <div className={PAGE_HEAD}><h1 className={PAGE_TITLE}>Admin: cases</h1></div>
      <form className="row" aria-label="Filter cases" onSubmit={(e) => e.preventDefault()}>
        <label>Status<select className={SELECT} value={status} onChange={(e) => { setStatus(e.target.value); setOffset(0); }}>
          <option value="">All statuses</option>{STATUSES.map((s) => <option key={s} value={s}>{STATUS_LABEL[s]}</option>)}</select></label>
        <label>Kind<select className={SELECT} value={kind} onChange={(e) => { setKind(e.target.value); setOffset(0); }}>
          <option value="">Both kinds</option><option value="copyright">Copyright notice</option><option value="likeness">Likeness report</option></select></label>
      </form>
      {problem ? <p className="error" role="alert">{problem}</p> : data === null ? <p className="muted">Loading…</p>
        : !data.cases.length ? <p className="muted">No cases{status || kind ? " match these filters" : " yet"}.</p>
        : <>
          <div className="table-wrap"><table className="ledger">
            <caption className="sr-only">Cases, newest first</caption>
            <thead><tr><th scope="col">Reference</th><th scope="col">Kind</th><th scope="col">Status</th><th scope="col">Reported by</th>
              <th scope="col" className="!text-left">Targets</th><th scope="col" className="!text-left">Created</th></tr></thead>
            <tbody>{data.cases.map((c) => (
              <tr key={c.reference}>
                <td className="whitespace-nowrap"><Link className={LINK} href={`/dashboard/admin/cases/?ref=${c.reference}`}>{c.reference}</Link></td>
                <td>{KIND_LABEL[c.kind] || c.kind}</td><td>{STATUS_LABEL[c.status] || c.status}</td>
                <td className="[overflow-wrap:anywhere]">{c.claimant_organization || c.claimant_name}</td>
                <td className="tabular-nums">{String(c.targets)}<span className="text-muted"> / {c.urls} link{c.urls === 1 ? "" : "s"}</span></td>
                <td className="!text-left whitespace-nowrap">{when(c.created_at)}</td>
              </tr>))}</tbody>
          </table></div>
          <nav className="row" aria-label="Pages">
            <p className="muted" aria-live="polite">{offset + 1}–{offset + data.cases.length} of {data.total}</p>
            <button type="button" className="btn small ghost" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>Previous</button>
            <button type="button" className="btn small ghost" disabled={offset + PAGE >= data.total} onClick={() => setOffset(offset + PAGE)}>Next</button>
          </nav>
        </>}
    </div>
  );
}

function CaseView({ reference }: { reference: string }) {
  const [c, setC] = useState<FullCase | null>(null), [problem, setProblem] = useState("");
  const [acting, setActing] = useState<Action | null>(null), [done, setDone] = useState<{ action: string; event: number } | null>(null);
  const load = useCallback(() => api<FullCase>(`/v1/admin/trust/cases/${encodeURIComponent(reference)}`).then(setC)
    .catch((e) => setProblem(e.message)), [reference]);
  useEffect(() => { setC(null); setDone(null); setProblem(""); load(); }, [load]);

  async function decide(action: Action, body: DecisionBody) {
    const prev = c?.events.length ? c.events[c.events.length - 1].id : 0;
    // The answer is the whole case as it now stands, history included: the page redraws from it.
    const fresh = await api<FullCase>(`/v1/admin/trust/cases/${encodeURIComponent(reference)}/decisions`, { body: { action, ...body } });
    setC(fresh);
    const mine = fresh.events.find((e) => e.id > prev && e.action === action);
    if (mine) { setDone({ action, event: mine.id }); focusSoon(`ev-${mine.id}`); }
  }

  const back = <div><Link className={LINK} href="/dashboard/admin/cases/">All cases</Link></div>;
  if (problem) return <div className="stack">{back}<p className="error" role="alert">{problem}</p></div>;
  if (!c) return <div className="stack">{back}<p className="muted">Loading…</p></div>;
  const allowed = ACTIONS.filter((a) => RULES[a].includes(c.status));
  const m = acting ? MEANING[acting] : null;

  return (
    <div className="stack">
      {back}
      <div className={PAGE_HEAD}>
        <h1 className={PAGE_TITLE}>{c.reference}</h1>
        <p className="flex flex-wrap gap-2 text-[14px]"><span className="rounded-full bg-chip px-[10px] py-[2px]">{KIND_LABEL[c.kind] || c.kind}</span>
          <span className="rounded-full bg-chip px-[10px] py-[2px] text-lime">{STATUS_LABEL[c.status] || c.status}</span></p>
      </div>
      {done && <p className="notice" role="status">Recorded: {MEANING[done.action as Action]?.label || done.action}. The new event is highlighted in the history below.</p>}

      <section className="panel" aria-labelledby="act-title">
        <h2 id="act-title" className="!mb-0">Decide</h2>
        <p className="muted small">Only the decisions a case that is {STATUS_LABEL[c.status]?.toLowerCase() || c.status} allows are shown.</p>
        <div className="flex flex-wrap gap-2">
          {allowed.map((a) => <button key={a} type="button" className={`btn small ${MEANING[a].danger ? "ghost !border-danger" : "ghost"}`}
            onClick={() => setActing(a)}>{MEANING[a].label}</button>)}
        </div>
      </section>

      <section className="panel" aria-labelledby="claimant-title">
        <h2 id="claimant-title" className="!mb-0">Claimant</h2>
        <Facts rows={[["Name", c.claimant.name], ["Email", c.claimant.email], ["Organisation", c.claimant.organization], ["Address", c.claimant.address],
          ["Phone", c.claimant.phone], ["Relationship", c.claimant.relationship], ["Signature", c.signature], ["Sender (hashed IP)", c.ip_hash.slice(0, 16) + "…"]]} />
      </section>

      <section className="panel" aria-labelledby="report-title">
        <h2 id="report-title" className="!mb-0">The report</h2>
        <Facts rows={[["The work or person", c.work], ["Details", c.details], ["Received", when(c.created_at)], ["Last change", when(c.updated_at)]]} />
        <div><h3 className="mb-2 text-[16px]">Reported links ({c.reported_urls.length})</h3>
          <ol className="grid gap-1 pl-6 text-[14px]">{c.reported_urls.map((u, i) => <li key={i} className="[overflow-wrap:anywhere]"><code>{u}</code></li>)}</ol></div>
      </section>

      <section className="panel" aria-labelledby="targets-title">
        <h2 id="targets-title" className="!mb-0">Content found ({c.targets.length})</h2>
        {!c.targets.length ? <p className="muted">None of the links point at content on ClutchClips.</p>
          : <ul className="grid list-none gap-2">{c.targets.map((t) => (
              <li key={t.kind + t.id} className="grid gap-1 rounded-8 bg-bg-2 px-3 py-2 text-[14px]">
                <p className="flex flex-wrap items-center gap-x-3"><span className="text-muted">{t.kind}</span><code className="[overflow-wrap:anywhere]">{t.id}</code>
                  <span className="ml-auto">{TARGET_LABEL[t.state] || t.state}</span></p>
                <p className="text-muted [overflow-wrap:anywhere]">Owner: {t.account_email || "(no email)"} · <code>{t.account_id}</code></p>
              </li>))}</ul>}
      </section>

      <section className="panel" aria-labelledby="history-title">
        <h2 id="history-title" className="!mb-0">History ({c.events.length})</h2>
        <ol className="grid list-none gap-2">{c.events.map((e) => (
          <li key={e.id} id={`ev-${e.id}`} tabIndex={-1}
            className={`grid gap-1 rounded-8 border border-solid px-3 py-2 text-[14px] ${done?.event === e.id ? "border-lime bg-lime-wash" : "border-line bg-bg-2"}`}>
            <p className="flex flex-wrap items-center gap-x-3"><b>{e.action}</b><span className="text-muted">by {e.actor_kind}{e.actor_id ? ` ${e.actor_id}` : ""}</span>
              <time className="ml-auto text-muted" dateTime={e.created_at}>{when(e.created_at)}</time></p>
            {e.note && <p className="whitespace-pre-wrap [overflow-wrap:anywhere]">{e.note}</p>}
            {e.data && <p className="text-muted [overflow-wrap:anywhere]">{Object.entries(e.data).map(([k, v]) => `${k}: ${typeof v === "object" ? JSON.stringify(v) : String(v)}`).join(" · ")}</p>}
          </li>))}</ol>
      </section>

      {acting && m && <DecisionDialog label={m.label} what={m.what} message={m.message}
        owners={acting === "terminate" ? owners(c) : undefined} danger={m.danger ? (account) => m.danger!(c, account) : undefined}
        onConfirm={(body) => decide(acting, body)} onClose={() => setActing(null)} />}
    </div>
  );
}

function Facts({ rows }: { rows: [string, string | null | undefined][] }) {
  return (
    <dl className="grid grid-cols-[minmax(0,11rem)_minmax(0,1fr)] gap-x-4 gap-y-2 text-[14px] narrow:grid-cols-1 [&_dd]:whitespace-pre-wrap [&_dd]:[overflow-wrap:anywhere] [&_dt]:text-muted narrow:[&_dd]:mb-2">
      {rows.map(([k, v]) => <div key={k} className="contents"><dt>{k}</dt><dd>{v || "—"}</dd></div>)}
    </dl>
  );
}
