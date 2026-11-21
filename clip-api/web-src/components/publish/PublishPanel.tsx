"use client";
// Select destination → edit caption → Publish now or Schedule. Honest pending/disabled states; no fake success.
import { FormEvent, useEffect, useMemo, useState } from "react";
import { api, ApiError } from "@/lib/api";
import {
  formatWhen, idemKey, loadAccounts, loadPlatforms, localZone, Platform, READINESS_LABEL, SocialAccount,
} from "@/lib/publish";

type TargetDraft = {
  social_account_id: string;
  title: string;
  caption: string;
  hashtags: string;
  privacy: string;
  options: Record<string, boolean>;
};

export function PublishPanel({ clipId, onClose }: { clipId: string; onClose: () => void }) {
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [reason, setReason] = useState<string>("");
  const [platforms, setPlatforms] = useState<Platform[]>([]);
  const [accounts, setAccounts] = useState<SocialAccount[]>([]);
  const [picked, setPicked] = useState<string | null>(null);
  const [draft, setDraft] = useState<TargetDraft | null>(null);
  const [when, setWhen] = useState<"now" | "later">("now");
  const [atLocal, setAtLocal] = useState("");
  const [rights, setRights] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [okMsg, setOkMsg] = useState("");
  const zone = useMemo(() => localZone(), []);

  useEffect(() => {
    let on = true;
    (async () => {
      try {
        const plat = await loadPlatforms();
        if (!on) return;
        setEnabled(plat.enabled);
        setReason(plat.reason || "");
        setPlatforms(plat.platforms);
        if (plat.enabled) setAccounts(await loadAccounts());
      } catch (e) {
        if (!on) return;
        setEnabled(false);
        setReason(e instanceof ApiError ? e.message : "Could not load publishing.");
      }
    })();
    return () => { on = false; };
  }, [clipId]);

  function pick(account: SocialAccount) {
    const plat = platforms.find((p) => p.id === account.platform);
    setPicked(account.id);
    setDraft({
      social_account_id: account.id,
      title: "",
      caption: "",
      hashtags: "",
      privacy: plat?.privacy_options[0] || (account.platform === "tiktok" ? "" : "public"),
      options: account.platform === "tiktok"
        ? { disable_comment: true, disable_duet: true, disable_stitch: true }
        : {},
    });
    setErr("");
    setOkMsg("");
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!draft || !picked) return;
    setBusy(true); setErr(""); setOkMsg("");
    try {
      const tags = draft.hashtags.split(/[\s,]+/).map((t) => t.replace(/^#/, "")).filter(Boolean);
      const publish_at = when === "later" && atLocal
        ? new Date(atLocal).toISOString()
        : null;
      const check = await api<any>(`/v1/clips/${clipId}/publish/check`, {
        body: { targets: [{
          social_account_id: draft.social_account_id,
          title: draft.title || null,
          caption: draft.caption,
          hashtags: tags,
          privacy: draft.privacy || null,
          options: draft.options,
        }] },
      });
      const t = check.targets?.[0];
      if (t && !t.ok) {
        setErr((t.reasons || []).join(" ") || "This clip cannot be published to that account yet.");
        setBusy(false);
        return;
      }
      // Prefill title/caption from defaults if the user left them empty.
      const title = draft.title || t?.defaults?.title || null;
      const caption = draft.caption || t?.defaults?.caption || "";
      const key = idemKey(clipId, [draft.social_account_id]);
      const { API, getToken } = await import("@/lib/api");
      const raw = await fetch(`${API}/v1/clips/${clipId}/publish`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${getToken()}`,
          "Idempotency-Key": key,
        },
        body: JSON.stringify({
          targets: [{
            social_account_id: draft.social_account_id,
            title, caption, hashtags: tags,
            privacy: draft.privacy || t?.defaults?.privacy || null,
            options: draft.options,
          }],
          publish_at,
          rights_confirmed: rights,
        }),
      });
      const text = await raw.text();
      const data = text ? JSON.parse(text) : null;
      if (!raw.ok) throw new ApiError(raw.status, data?.error?.code || "error", data?.error?.message || "Publish failed.");
      const post = data.posts?.[0];
      const label = post?.status === "SCHEDULED"
        ? `Scheduled for ${formatWhen(post.publish_at, zone)}`
        : `Queued (${post?.status || "QUEUED"})`;
      setOkMsg(`${label}. Track status in Calendar.`);
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Publish failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid gap-4 rounded-20 border border-solid border-line-soft bg-card p-5" role="dialog" aria-label="Publish clip">
      <div className="flex items-start justify-between gap-3">
        <div className="grid gap-1">
          <h2 className="m-0 text-[18px] font-semibold">Publish</h2>
          <p className="m-0 text-[13px] text-muted">Times shown in {zone}. Destinations stay pending until ClutchClips is approved on each platform.</p>
        </div>
        <button type="button" className="btn small ghost" onClick={onClose}>Close</button>
      </div>

      {enabled === null && <p className="m-0 text-[14px] text-muted">Checking publishing…</p>}
      {enabled === false && (
        <p className="m-0 rounded-12 border border-solid border-line-soft bg-panel p-4 text-[14px] text-muted">
          {reason || "Publishing is not enabled yet."} You can still download the clip and post it yourself.
        </p>
      )}

      {enabled && (
        <>
          <section className="grid gap-2" aria-label="Connected accounts">
            <h3 className="m-0 text-[14px] font-medium">Destination</h3>
            {!accounts.length && (
              <p className="m-0 text-[13px] text-muted">
                No accounts connected.{" "}
                <a href="/dashboard/social-accounts/" className="text-cyan underline-offset-2 hover:underline">Connect an account</a>
                {" "}first. Platforms without server credentials stay disabled.
              </p>
            )}
            <ul className="m-0 grid list-none gap-2 p-0">
              {accounts.map((a) => {
                const plat = platforms.find((p) => p.id === a.platform);
                const blocked = !plat?.configured || a.status !== "active" || plat.readiness === "not_configured";
                return (
                  <li key={a.id}>
                    <button type="button" disabled={blocked}
                      onClick={() => pick(a)}
                      className={`flex w-full items-center justify-between gap-3 rounded-12 border border-solid px-3 py-2 text-left ${picked === a.id ? "border-lime bg-panel" : "border-line-soft bg-transparent"} ${blocked ? "cursor-default opacity-50" : "cursor-pointer hover:border-lime"}`}>
                      <span className="grid gap-0.5">
                        <span className="text-[14px] font-medium text-text">{a.display_name || a.platform}</span>
                        <span className="text-[12px] text-muted">{plat?.name || a.platform} · {READINESS_LABEL[plat?.readiness || "not_configured"]}</span>
                      </span>
                      {a.status === "needs_reconnect" && <span className="text-[12px] text-amber">Reconnect</span>}
                    </button>
                  </li>
                );
              })}
            </ul>
            {platforms.filter((p) => !p.configured).map((p) => (
              <p key={p.id} className="m-0 text-[12.5px] text-fg-3">{p.name}: {READINESS_LABEL[p.readiness]}.</p>
            ))}
          </section>

          {draft && (
            <form className="grid gap-3" onSubmit={submit}>
              <label className="grid gap-1 text-[13px]">
                <span className="text-muted">Title</span>
                <input className="input" value={draft.title} onChange={(e) => setDraft({ ...draft, title: e.target.value })} maxLength={300} />
              </label>
              <label className="grid gap-1 text-[13px]">
                <span className="text-muted">Caption</span>
                <textarea className="input min-h-[88px]" value={draft.caption} onChange={(e) => setDraft({ ...draft, caption: e.target.value })} maxLength={5000} />
              </label>
              <label className="grid gap-1 text-[13px]">
                <span className="text-muted">Hashtags (space or comma separated)</span>
                <input className="input" value={draft.hashtags} onChange={(e) => setDraft({ ...draft, hashtags: e.target.value })} />
              </label>
              <label className="grid gap-1 text-[13px]">
                <span className="text-muted">Visibility{accounts.find((a) => a.id === picked)?.platform === "tiktok" ? " (required, no default)" : ""}</span>
                <select className="input" value={draft.privacy} onChange={(e) => setDraft({ ...draft, privacy: e.target.value })} required={accounts.find((a) => a.id === picked)?.platform === "tiktok"}>
                  <option value="">Choose…</option>
                  {(platforms.find((p) => p.id === accounts.find((a) => a.id === picked)?.platform)?.privacy_options.length
                    ? platforms.find((p) => p.id === accounts.find((a) => a.id === picked)?.platform)!.privacy_options
                    : ["PUBLIC_TO_EVERYONE", "MUTUAL_FOLLOW_FRIENDS", "SELF_ONLY"]).map((v) => (
                    <option key={v} value={v}>{v}</option>
                  ))}
                </select>
              </label>
              <fieldset className="grid gap-2 border-0 p-0">
                <legend className="text-[13px] text-muted">When</legend>
                <label className="inline-flex items-center gap-2 text-[14px]">
                  <input type="radio" checked={when === "now"} onChange={() => setWhen("now")} /> Publish now
                </label>
                <label className="inline-flex items-center gap-2 text-[14px]">
                  <input type="radio" checked={when === "later"} onChange={() => setWhen("later")} /> Schedule
                </label>
                {when === "later" && (
                  <input type="datetime-local" className="input" required value={atLocal}
                    onChange={(e) => setAtLocal(e.target.value)} />
                )}
              </fieldset>
              <label className="inline-flex items-start gap-2 text-[13px] text-muted">
                <input type="checkbox" checked={rights} onChange={(e) => setRights(e.target.checked)} required className="mt-1" />
                I have the rights to post this clip on the selected account.
              </label>
              <p className="m-0 text-[12.5px] text-fg-3">Cost: Free. Nothing is sent until you confirm. No success toast unless the job is actually queued.</p>
              {err && <p className="m-0 text-[13px] text-rose" role="alert">{err}</p>}
              {okMsg && <p className="m-0 text-[13px] text-lime" role="status">{okMsg}</p>}
              <div className="flex flex-wrap gap-2">
                <button type="submit" className="btn primary" disabled={busy || !rights}>{busy ? "Working…" : when === "later" ? "Schedule" : "Publish"}</button>
                <a href="/dashboard/calendar/" className="btn ghost">Open calendar</a>
              </div>
            </form>
          )}
        </>
      )}
    </div>
  );
}
