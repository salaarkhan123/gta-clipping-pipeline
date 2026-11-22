"use client";
// Reports about my content: GET /v1/trust/my-cases. `?ref=` opens one case, with the counter-notice form when the
// API says one may be sent (`can_counter_notice`). The claimant's contact details are never in this response.
import Link from "next/link";
import { EmptyState } from "@/components/ui/EmptyState";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";
import { ImportTakedown } from "@/components/dash/ImportTakedown";
import { useDash } from "@/components/dash/Shell";
import { BackTitle, PAGE_HEAD } from "@/components/dash/ui";
import { CounterNoticeForm } from "@/components/trust/CounterNoticeForm";
import { LINK } from "@/components/trust/Field";
import { api, ApiError } from "@/lib/api";
import { focusSoon, KIND_LABEL, STATUS_LABEL, TARGET_LABEL, when } from "@/lib/trust";

type MyCase = { reference: string; kind: string; status: string; reported_by: string; work: string; created_at: string;
  your_content: { kind: string; id: string; state: string }[]; can_counter_notice: boolean };

// useSearchParams needs a Suspense boundary in a static export.
export default function CasesPage() { return <Suspense><Cases /></Suspense>; }

function Cases() {
  const { fail } = useDash();
  const ref = (useSearchParams().get("ref") || "").trim().toUpperCase();
  const [cases, setCases] = useState<MyCase[] | null>(null), [sent, setSent] = useState("");
  const load = useCallback(() => api<{ cases: MyCase[] }>("/v1/trust/my-cases").then((r) => setCases(r.cases)).catch(fail), [fail]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => setSent(""), [ref]);
  const open = ref ? cases?.find((c) => c.reference === ref) : undefined;

  return (
    <div className="stack">
      <div className={PAGE_HEAD}><BackTitle title="Reports about my content" crumbs={[{ label: "Home", href: "/dashboard/" }, { label: "Reports about my content" }]} /></div>
      <p className="muted">Copyright and likeness reports that point at your uploads or clips. A person at ClutchClips reviews every report;
        we email you when one is forwarded to you or when your content is disabled, removed or restored.</p>
      {cases === null ? <p className="muted">Loading…</p>
        : ref ? (open ? <CaseDetail c={open} sent={sent} onSent={(c) => {
            setCases((all) => (all || []).map((x) => (x.reference === c.reference ? c : x)));
            setSent("Your counter-notice was sent. A copy went to the person who reported your content. Unless they tell us within 10 business days that they have filed a court action, an admin may restore your content.");
            focusSoon("case-sent");
          }} />
          : <section className="panel"><p role="alert">No case {ref} on your account.</p><div><Link className={LINK} href="/dashboard/cases/">See all reports</Link></div></section>)
        : !cases.length ? <EmptyState icon="check" title="No reports about your content">Nothing to do.</EmptyState>
        : <ul className="grid list-none gap-3" aria-label="Reports">
            {cases.map((c) => (
              <li key={c.reference} className="grid gap-2 rounded-16 bg-card p-4">
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                  <Link className="font-display text-[16px] font-semibold text-lime underline" href={`/dashboard/cases/?ref=${c.reference}`}>{c.reference}</Link>
                  <span className="text-[14px] text-muted">{KIND_LABEL[c.kind] || c.kind}</span>
                  <span className="ml-auto rounded-[6px] bg-control px-[8px] py-[3px] text-[12px]">{STATUS_LABEL[c.status] || c.status}</span>
                </div>
                <p className="text-[14px]"><span className="text-muted">Reported by</span> {c.reported_by} · <span className="text-muted">{when(c.created_at)}</span></p>
                <p className="line-clamp-2 text-[14px] text-soft [overflow-wrap:anywhere]">{c.work}</p>
                <p className="text-[14px] text-muted">{c.your_content.length} item{c.your_content.length === 1 ? "" : "s"} of yours
                  {c.can_counter_notice && <> · <b className="text-warn">You can send a counter-notice</b></>}</p>
              </li>))}
          </ul>}
      {!ref && <div id="remove-imports"><ImportTakedown /></div>}
    </div>
  );
}

function CaseDetail({ c, sent, onSent }: { c: MyCase; sent: string; onSent: (c: MyCase) => void }) {
  return (
    <>
      <div><Link className={LINK} href="/dashboard/cases/">All reports about my content</Link></div>
      {sent && <p id="case-sent" className="notice" role="status" tabIndex={-1}>{sent}</p>}
      <section className="panel" aria-labelledby="case-title">
        <div className="flex flex-wrap items-center gap-3">
          <h2 id="case-title" className="!m-0 font-display text-[22px]">{c.reference}</h2>
          <span className="rounded-[6px] bg-control px-[8px] py-[3px] text-[12px]">{STATUS_LABEL[c.status] || c.status}</span>
        </div>
        <dl className="grid grid-cols-[minmax(0,10rem)_minmax(0,1fr)] gap-x-4 gap-y-2 text-[14px] narrow:grid-cols-1 [&_dd]:[overflow-wrap:anywhere] [&_dt]:text-muted narrow:[&_dd]:mb-2">
          <dt>Kind</dt><dd>{KIND_LABEL[c.kind] || c.kind}</dd>
          <dt>Reported by</dt><dd>{c.reported_by}</dd>
          <dt>Received</dt><dd>{when(c.created_at)}</dd>
          <dt>The work or person</dt><dd className="whitespace-pre-wrap">{c.work}</dd>
        </dl>
        <div>
          <h3 className="mb-2 text-[16px]">Your content in this case</h3>
          {!c.your_content.length ? <p className="muted">None found.</p>
            : <ul className="grid list-none gap-2">{c.your_content.map((t) => (
                <li key={t.kind + t.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-8 bg-bg-2 px-3 py-2 text-[14px]">
                  <span className="text-muted">{t.kind}</span><code className="[overflow-wrap:anywhere]">{t.id}</code>
                  <span className="ml-auto">{TARGET_LABEL[t.state] || t.state}</span></li>))}</ul>}
        </div>
      </section>
      {c.can_counter_notice ? <section className="panel"><CounterNoticeForm reference={c.reference} onSent={onSent} /></section>
        : !sent && <p className="muted small">{c.status === "counter_noticed" ? "Your counter-notice was sent. An admin decides on restoring your content after 10 business days."
            : ["received", "in_review", "info_requested"].includes(c.status) ? "Nothing has been taken down by this case. If your content is disabled or removed, you can send a counter-notice here."
            : "A counter-notice is possible only while your content is disabled or removed."}</p>}
    </>
  );
}
