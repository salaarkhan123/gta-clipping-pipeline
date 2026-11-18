"use client";
// Account settings: who you are, the policies you accepted, a copy of your data, and deleting the account (#149).
// Uses the public API only: GET /v1/me/consents, GET /v1/legal/policies, GET /v1/me/export, POST /v1/me/delete.
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Icon } from "@/components/dash/Icon";
import { useDash } from "@/components/dash/Shell";
import { PAGE_HEAD, PAGE_TITLE } from "@/components/dash/ui";
import { api, ApiError, setToken } from "@/lib/api";

type Acceptance = { policy: string; version: string; accepted_at: string };
const day = (iso: string) => new Date(iso).toLocaleDateString(undefined, { year: "numeric", month: "long", day: "numeric" });

export default function Account() {
  const { me, fail } = useDash();
  const router = useRouter();
  const [accepted, setAccepted] = useState<Acceptance[] | null>(null);
  const [titles, setTitles] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [password, setPassword] = useState(""), [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false), [refused, setRefused] = useState("");
  const plan = me.plan[0].toUpperCase() + me.plan.slice(1);

  useEffect(() => {
    api("/v1/me/consents").then((r) => setAccepted(r.acceptances)).catch(fail);
    api("/v1/legal/policies", { auth: false })
      .then((r) => setTitles(Object.fromEntries(r.policies.map((p: any) => [p.id, p.title])))).catch(() => {});
  }, [fail]);

  const download = async () => {
    setSaving(true);
    try {
      const data = await api("/v1/me/export");
      const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
      const a = Object.assign(document.createElement("a"), { href: url, download: `clutchclips-data-${new Date().toISOString().slice(0, 10)}.json` });
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) { fail(e); } finally { setSaving(false); }
  };

  const remove = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setRefused("");
    try {
      await api("/v1/me/delete", { body: { password, confirm } });
      setToken(null);
      router.push("/");
    } catch (err) {
      if (err instanceof ApiError && [403, 409, 429].includes(err.status)) setRefused(err.message);
      else fail(err);
    } finally { setBusy(false); }
  };

  return (
    <div className="stack">
      <div className={PAGE_HEAD}><h1 className={PAGE_TITLE}>Account</h1></div>

      <section className="panel" aria-labelledby="who-title">
        <h2 id="who-title">Your account</h2>
        <dl className="grid grid-cols-[max-content_1fr] gap-x-6 gap-y-2 text-[14px] narrow:grid-cols-1 narrow:gap-y-1">
          <dt className="muted">Email</dt><dd className="[overflow-wrap:anywhere]">{me.email}</dd>
          <dt className="muted">Plan</dt><dd>{plan}</dd>
          <dt className="muted">Member since</dt><dd>{day(me.created_at)}</dd>
        </dl>
      </section>

      <section className="panel" aria-labelledby="policies-title">
        <h2 id="policies-title">Policies you accepted</h2>
        {accepted === null ? <p className="muted">Loading…</p> : !accepted.length ? <p className="muted">No policy acceptance on record yet.</p>
          : <ul className="grid list-none gap-2 text-[14px]">{accepted.map((a) => (
              <li key={`${a.policy}-${a.version}`} className="flex flex-wrap justify-between gap-x-4">
                <span>{titles[a.policy] || a.policy} <span className="muted">version {a.version}</span></span>
                <span className="muted">accepted {day(a.accepted_at)}</span></li>))}</ul>}
      </section>

      <section className="panel" aria-labelledby="data-title">
        <h2 id="data-title">Download my data</h2>
        <p className="muted text-[14px]">A JSON file with everything we hold about your account: your profile, accepted policies, uploads, jobs,
          clips, saved looks, API key names, credit history, payments, link imports and any reports about your content.
          Videos and clips are not in it: download those from your library.</p>
        <div><button className="btn small ghost" onClick={download} disabled={saving}>
          <Icon name="download" size={16} /> {saving ? "Preparing…" : "Download my data"}</button></div>
      </section>

      <section className="panel" aria-labelledby="delete-title">
        <h2 id="delete-title">Delete my account</h2>
        <div className="grid gap-3 text-[14px]">
          <p><strong>This cannot be undone.</strong> Deleting your account removes:</p>
          <ul className="grid list-disc gap-1 pl-5">
            <li>every upload, transcript, clip, thumbnail and export, and their files</li>
            <li>your saved looks and API keys (your apps stop working at once)</li>
            <li>your email, password, sign-up IP address and billing link</li>
            <li>any credits left on the account</li>
          </ul>
          <p>We keep, with no name or email attached: your credit and payment records, which our accounts need. We
            also keep the records the law requires, such as copyright notices about your content for up to a year,
            and the policies you accepted.</p>
          <p className="muted">A paid plan must be cancelled first (Billing, then Manage billing). If a copyright or likeness
            report about your content is open, write to support@clutchclips.io and we will help.</p>
        </div>
        <form className="grid max-w-[420px] gap-3" onSubmit={remove}>
          <label className="grid gap-1 text-[14px]">Your password
            <input type="password" required autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} /></label>
          <label className="grid gap-1 text-[14px]">Type DELETE to confirm
            <input required autoComplete="off" spellCheck={false} value={confirm} onChange={(e) => setConfirm(e.target.value)} /></label>
          {refused && <p className="error" role="alert">{refused}</p>}
          <div><button className="btn small ghost danger" type="submit" disabled={busy || !password || confirm !== "DELETE"}>
            <Icon name="trash" size={16} /> {busy ? "Deleting…" : "Delete my account"}</button></div>
        </form>
      </section>
    </div>
  );
}
