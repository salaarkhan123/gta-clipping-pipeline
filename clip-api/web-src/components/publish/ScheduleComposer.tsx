"use client";
// Create a scheduled post from an exported clip, or edit an existing SCHEDULED row. Reuses publish APIs only.
import { FormEvent, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { api, ApiError, API, getToken } from "@/lib/api";
import {
  formatWhen, idemKey, loadAccounts, loadPlatforms, localZone, Platform,
  PLATFORM_LABEL, Post, SocialAccount, toLocalInputValue,
} from "@/lib/publish";

type ClipRow = {
  id: string;
  title?: string | null;
  hook?: string | null;
  export_url?: string | null;
  start_sec?: number | null;
  end_sec?: number | null;
};

type Props = {
  onClose: () => void;
  onSaved: () => void;
  /** Prefill when editing a scheduled post. */
  editing?: Post | null;
  /** Prefill clip when opened from a day cell. */
  initialAtLocal?: string;
};

export function ScheduleComposer({ onClose, onSaved, editing, initialAtLocal }: Props) {
  const zone = useMemo(() => localZone(), []);
  const [platforms, setPlatforms] = useState<Platform[]>([]);
  const [accounts, setAccounts] = useState<SocialAccount[]>([]);
  const [clips, setClips] = useState<ClipRow[]>([]);
  const [clipId, setClipId] = useState(editing?.clip_id || "");
  const [accountId, setAccountId] = useState(editing?.social_account_id || "");
  const [title, setTitle] = useState(editing?.title || "");
  const [caption, setCaption] = useState(editing?.caption || "");
  const [hashtags, setHashtags] = useState((editing?.hashtags || []).join(" "));
  const [privacy, setPrivacy] = useState(editing?.privacy || "");
  const [atLocal, setAtLocal] = useState(
    editing ? toLocalInputValue(editing.publish_at) : (initialAtLocal || ""),
  );
  const [rights, setRights] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [loadErr, setLoadErr] = useState("");

  useEffect(() => {
    let on = true;
    (async () => {
      try {
        const [plat, acc, clipRes] = await Promise.all([
          loadPlatforms(),
          loadAccounts(),
          api<{ clips: ClipRow[] }>("/v1/clips?limit=40&offset=0&sort=newest&filter=all"),
        ]);
        if (!on) return;
        setPlatforms(plat.platforms);
        const active = acc.filter((a) => a.status === "active");
        setAccounts(active);
        // export_url is set only when export_key exists — publish requires a finished export.
        const exported = (clipRes.clips || []).filter((c) => !!c.export_url);
        setClips(exported);
        setClipId((prev) => prev || (editing?.clip_id || exported[0]?.id || ""));
        setAccountId((prev) => prev || (editing?.social_account_id || active[0]?.id || ""));
      } catch (e) {
        if (!on) return;
        setLoadErr(e instanceof ApiError ? e.message : "Could not load schedule form.");
      }
    })();
    return () => { on = false; };
  }, [editing]);

  const pickedAccount = accounts.find((a) => a.id === accountId);
  const plat = platforms.find((p) => p.id === pickedAccount?.platform);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true); setErr("");
    try {
      const tags = hashtags.split(/[\s,]+/).map((t) => t.replace(/^#/, "")).filter(Boolean);
      const publish_at = atLocal ? new Date(atLocal).toISOString() : null;
      if (!publish_at) throw new ApiError(400, "schedule_required", "Pick a date and time.");

      if (editing) {
        await api(`/v1/posts/${editing.id}`, {
          method: "PATCH",
          body: {
            title: title || null,
            caption,
            hashtags: tags,
            privacy: privacy || null,
            publish_at,
          },
        });
        onSaved();
        onClose();
        return;
      }

      if (!clipId || !accountId) throw new ApiError(400, "missing", "Pick a clip and destination.");
      const target = {
        social_account_id: accountId,
        title: title || null,
        caption,
        hashtags: tags,
        privacy: privacy || null,
        options: pickedAccount?.platform === "tiktok"
          ? { disable_comment: true, disable_duet: true, disable_stitch: true }
          : {},
      };
      const check = await api<{ targets: Array<{ ok: boolean; reasons?: string[]; defaults?: Record<string, string> }> }>(
        `/v1/clips/${clipId}/publish/check`,
        { body: { targets: [target] } },
      );
      const t = check.targets?.[0];
      if (t && !t.ok) {
        setErr((t.reasons || []).join(" ") || "This clip cannot be scheduled to that account yet.");
        setBusy(false);
        return;
      }
      const key = idemKey(clipId, [accountId]);
      const raw = await fetch(`${API}/v1/clips/${clipId}/publish`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${getToken()}`,
          "Idempotency-Key": key,
        },
        body: JSON.stringify({
          targets: [{
            ...target,
            title: title || t?.defaults?.title || null,
            caption: caption || t?.defaults?.caption || "",
            privacy: privacy || t?.defaults?.privacy || null,
          }],
          publish_at,
          rights_confirmed: rights,
        }),
      });
      const text = await raw.text();
      const data = text ? JSON.parse(text) : null;
      if (!raw.ok) throw new ApiError(raw.status, data?.error?.code || "error", data?.error?.message || "Schedule failed.");
      onSaved();
      onClose();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Schedule failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      className="grid gap-4 rounded-20 border border-solid border-line-soft bg-card p-5 shadow-pop"
      role="dialog"
      aria-label={editing ? "Edit scheduled post" : "Schedule a clip"}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="grid gap-1">
          <h2 className="m-0 text-[18px] font-semibold">
            {editing ? "Edit schedule" : "Schedule a clip"}
          </h2>
          <p className="m-0 text-[13px] text-muted">
            Times in {zone}. Only exported clips can be queued. Nothing posts until the scheduled job runs.
          </p>
        </div>
        <button type="button" className="btn small ghost" onClick={onClose}>Close</button>
      </div>

      {loadErr && <p className="m-0 text-[13px] text-danger" role="alert">{loadErr}</p>}

      <form className="grid gap-3" onSubmit={submit}>
        {!editing && (
          <label className="grid gap-1 text-[13px]">
            <span className="text-muted">Exported clip</span>
            {!clips.length ? (
              <p className="m-0 text-[13px] text-muted">
                No exported clips yet.{" "}
                <Link href="/dashboard/library/?view=clips" className="text-cyan underline-offset-2 hover:underline">
                  Export from Library
                </Link>
                {" "}first — publish never starts a paid render.
              </p>
            ) : (
              <select className="input" required value={clipId} onChange={(e) => setClipId(e.target.value)}>
                {clips.map((c) => {
                  const secs = (c.end_sec != null && c.start_sec != null)
                    ? Math.max(0, Math.round(c.end_sec - c.start_sec)) : null;
                  return (
                    <option key={c.id} value={c.id}>
                      {(c.title || c.hook || c.id).slice(0, 80)}
                      {secs != null ? ` · ${secs}s` : ""}
                    </option>
                  );
                })}
              </select>
            )}
          </label>
        )}

        {!editing && (
          <label className="grid gap-1 text-[13px]">
            <span className="text-muted">Destination</span>
            {!accounts.length ? (
              <p className="m-0 text-[13px] text-muted">
                No connected accounts.{" "}
                <Link href="/dashboard/social-accounts/" className="text-cyan underline-offset-2 hover:underline">
                  Connect one
                </Link>
                .
              </p>
            ) : (
              <select className="input" required value={accountId} onChange={(e) => setAccountId(e.target.value)}>
                {accounts.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.display_name || PLATFORM_LABEL[a.platform] || a.platform}
                    {" · "}
                    {PLATFORM_LABEL[a.platform] || a.platform}
                  </option>
                ))}
              </select>
            )}
          </label>
        )}

        {editing && (
          <p className="m-0 text-[13px] text-muted">
            {PLATFORM_LABEL[editing.platform] || editing.platform}
            {" · "}
            clip {editing.clip_id}
          </p>
        )}

        <label className="grid gap-1 text-[13px]">
          <span className="text-muted">Publish at ({zone})</span>
          <input type="datetime-local" className="input" required value={atLocal}
            onChange={(e) => setAtLocal(e.target.value)} />
        </label>

        <label className="grid gap-1 text-[13px]">
          <span className="text-muted">Title</span>
          <input className="input" value={title} onChange={(e) => setTitle(e.target.value)} maxLength={300} />
        </label>
        <label className="grid gap-1 text-[13px]">
          <span className="text-muted">Caption</span>
          <textarea className="input min-h-[72px]" value={caption} onChange={(e) => setCaption(e.target.value)} maxLength={5000} />
        </label>
        <label className="grid gap-1 text-[13px]">
          <span className="text-muted">Hashtags</span>
          <input className="input" value={hashtags} onChange={(e) => setHashtags(e.target.value)}
            placeholder="gta clutch ranked" />
        </label>

        {(plat?.privacy_options?.length || pickedAccount?.platform === "tiktok") && (
          <label className="grid gap-1 text-[13px]">
            <span className="text-muted">Visibility</span>
            <select className="input" value={privacy} onChange={(e) => setPrivacy(e.target.value)}
              required={pickedAccount?.platform === "tiktok"}>
              <option value="">Choose…</option>
              {(plat?.privacy_options?.length
                ? plat.privacy_options
                : ["PUBLIC_TO_EVERYONE", "MUTUAL_FOLLOW_FRIENDS", "SELF_ONLY"]
              ).map((v) => <option key={v} value={v}>{v}</option>)}
            </select>
          </label>
        )}

        {!editing && (
          <label className="inline-flex items-start gap-2 text-[13px] text-muted">
            <input type="checkbox" className="mt-1" checked={rights} onChange={(e) => setRights(e.target.checked)} required />
            I have the rights to post this clip on the selected account.
          </label>
        )}

        <p className="m-0 text-[12.5px] text-fg-3">
          Cost: Free. Preview shows {atLocal ? formatWhen(new Date(atLocal).toISOString(), zone) : "—"}.
        </p>
        {err && <p className="m-0 text-[13px] text-danger" role="alert">{err}</p>}
        <div className="flex flex-wrap gap-2">
          <button type="submit" className="btn primary" disabled={busy || (!editing && !rights)}>
            {busy ? "Saving…" : editing ? "Save changes" : "Schedule"}
          </button>
          <button type="button" className="btn ghost" onClick={onClose}>Cancel</button>
        </div>
      </form>
    </div>
  );
}
