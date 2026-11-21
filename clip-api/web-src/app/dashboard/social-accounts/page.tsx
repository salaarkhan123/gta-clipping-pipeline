"use client";
// Connect / disconnect social destinations. Tokens never reach this page.
import { Suspense, useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { useDash } from "@/components/dash/Shell";
import { PAGE_HEAD, PAGE_TITLE } from "@/components/dash/ui";
import {
  loadAccounts, loadPlatforms, Platform, READINESS_LABEL, SocialAccount,
} from "@/lib/publish";

// useSearchParams needs a Suspense boundary in a static export.
export default function SocialAccountsPage() {
  return <Suspense><SocialAccounts /></Suspense>;
}

function SocialAccounts() {
  const { fail } = useDash();
  const params = useSearchParams();
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [reason, setReason] = useState("");
  const [platforms, setPlatforms] = useState<Platform[]>([]);
  const [accounts, setAccounts] = useState<SocialAccount[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [note, setNote] = useState("");

  const reload = useCallback(async () => {
    try {
      const plat = await loadPlatforms();
      setEnabled(plat.enabled);
      setReason(plat.reason || "");
      setPlatforms(plat.platforms);
      if (plat.enabled) setAccounts(await loadAccounts());
      else setAccounts([]);
    } catch (e) {
      fail(e);
    }
  }, [fail]);

  useEffect(() => { reload(); }, [reload]);
  useEffect(() => {
    if (params.get("connected")) setNote("Account connected.");
    if (params.get("error") === "oauth_denied") setNote("Connect was canceled.");
    if (params.get("error") === "oauth_failed") setNote("Connect failed. Try again.");
  }, [params]);

  async function connect(platform: string) {
    setBusy(platform); setNote("");
    try {
      const r = await api<{ authorize_url: string }>(`/v1/social-accounts/${platform}/connect`, { method: "POST", body: {} });
      window.location.href = r.authorize_url;
    } catch (e) {
      setNote(e instanceof ApiError ? e.message : "Could not start connect.");
      setBusy(null);
    }
  }

  async function disconnect(id: string) {
    setBusy(id); setNote("");
    try {
      await api(`/v1/social-accounts/${id}`, { method: "DELETE" });
      setNote("Disconnected. Pending posts for that account were canceled.");
      await reload();
    } catch (e) {
      setNote(e instanceof ApiError ? e.message : "Could not disconnect.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="grid gap-6">
      <div className={PAGE_HEAD}>
        <div className="grid gap-1">
          <h1 className={PAGE_TITLE}>Social accounts</h1>
          <p className="m-0 max-w-[56ch] text-[14px] text-muted">
            Connect the accounts you own. ClutchClips uses official OAuth only. Access tokens stay on the server and never appear here.
          </p>
        </div>
      </div>

      {enabled === false && (
        <p className="m-0 rounded-20 border border-solid border-line-soft bg-card p-5 text-[14px] text-muted">
          {reason || "Publishing is not enabled on this server yet."} Destinations will appear here after the owner turns publishing on and registers each platform app.
        </p>
      )}

      {note && <p className="m-0 text-[13px] text-cyan" role="status">{note}</p>}

      {enabled && (
        <>
          <section className="grid gap-3" aria-labelledby="connected-title">
            <h2 id="connected-title" className="m-0 text-[18px]">Connected</h2>
            {!accounts.length && <p className="m-0 text-[14px] text-muted">None yet.</p>}
            <ul className="m-0 grid list-none gap-2 p-0">
              {accounts.map((a) => (
                <li key={a.id} className="flex flex-wrap items-center justify-between gap-3 rounded-20 border border-solid border-line-soft bg-card px-4 py-3">
                  <div className="grid gap-0.5">
                    <span className="text-[15px] font-medium">{a.display_name || a.platform}</span>
                    <span className="text-[12.5px] text-muted">{a.platform} · {a.status}</span>
                  </div>
                  <button type="button" className="btn small ghost" disabled={busy === a.id}
                    onClick={() => disconnect(a.id)}>Disconnect</button>
                </li>
              ))}
            </ul>
          </section>

          <section className="grid gap-3" aria-labelledby="available-title">
            <h2 id="available-title" className="m-0 text-[18px]">Available destinations</h2>
            <ul className="m-0 grid list-none gap-2 p-0">
              {platforms.map((p) => {
                const can = p.configured && p.readiness !== "held";
                return (
                  <li key={p.id} className="grid gap-2 rounded-20 border border-solid border-line-soft bg-card p-4">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div className="grid gap-0.5">
                        <span className="text-[15px] font-medium">{p.name}</span>
                        <span className="text-[12.5px] text-muted">{READINESS_LABEL[p.readiness]}{p.operational ? "" : " · not live"}</span>
                      </div>
                      <button type="button" className="btn small primary" disabled={!can || busy === p.id}
                        title={can ? `Connect ${p.name}` : READINESS_LABEL[p.readiness]}
                        onClick={() => connect(p.id)}>
                        {busy === p.id ? "Starting…" : can ? "Connect" : "Unavailable"}
                      </button>
                    </div>
                    {p.notes?.length > 0 && (
                      <ul className="m-0 grid list-disc gap-1 pl-4 text-[12.5px] text-fg-3">
                        {p.notes.map((n) => <li key={n}>{n}</li>)}
                      </ul>
                    )}
                  </li>
                );
              })}
            </ul>
          </section>
        </>
      )}
    </div>
  );
}
