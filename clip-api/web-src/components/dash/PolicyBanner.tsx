"use client";
import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import { POLICIES } from "@/lib/legal";
import { useDash } from "./Shell";

// Shown while GET /v1/me says `consent_required`: a required policy has a version this account has not accepted.
// Accept sends the versions the API serves now (GET /v1/legal/policies) for the ids in `consents_missing`; a 409
// means a version changed since, so the page reloads to show the new one.
export function PolicyBanner() {
  const { me, reloadMe } = useDash();
  const [busy, setBusy] = useState(false), [problem, setProblem] = useState("");
  if (!me?.consent_required) return null;
  const missing: string[] = me.consents_missing || [];
  const links = POLICIES.filter((p) => missing.includes(p.id));

  async function accept() {
    setBusy(true); setProblem("");
    try {
      const { policies } = await api<{ policies: { id: string; version: string }[] }>("/v1/legal/policies", { auth: false });
      const versions = Object.fromEntries(policies.filter((p) => missing.includes(p.id)).map((p) => [p.id, p.version]));
      await api("/v1/me/consents", { body: { policies: versions } });
      await reloadMe();
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) { window.location.reload(); return; }
      setProblem(e instanceof Error ? e.message : "Could not save. Try again.");
      setBusy(false);
    }
  }

  return (
    <div className="notice mx-0 mb-6 flex max-w-none flex-wrap items-center gap-x-4 gap-y-2" role="region" aria-label="Policy update">
      <p className="min-w-0 flex-1">
        <b>We&apos;ve updated our policies.</b> Please read{" "}
        {links.map((p, i) => <span key={p.id}>{i > 0 && (i === links.length - 1 ? " and " : ", ")}
          <a href={p.path} target="_blank" rel="noopener" className="text-lime underline">{p.title}</a></span>)}, then accept.
      </p>
      <button type="button" className="btn small primary" disabled={busy} onClick={accept}>{busy ? "Saving…" : "Accept"}</button>
      {problem && <p className="error w-full" role="alert">{problem}</p>}
    </div>
  );
}
