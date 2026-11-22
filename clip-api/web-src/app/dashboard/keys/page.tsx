"use client";
import { useCallback, useEffect, useState } from "react";
import { Icon } from "@/components/dash/Icon";
import { useDash } from "@/components/dash/Shell";
import { PageHeader } from "@/components/ui/PageHeader";
import { API, api } from "@/lib/api";

export default function Keys() {
  const { fail } = useDash();
  const [keys, setKeys] = useState<any[] | null>(null), [fresh, setFresh] = useState("");
  const load = useCallback(() => api("/v1/keys").then((r) => setKeys(r.keys)).catch(fail), [fail]);
  useEffect(() => { load(); }, [load]);

  return (
    <>
      <PageHeader title="API access">
        <a className="btn small ghost" href={`${API}/docs`} target="_blank" rel="noreferrer">OpenAPI reference <Icon name="external" size={16} /></a>
      </PageHeader>
      <p className="m-0 max-w-[70ch] text-[14px] leading-[1.55] text-fg-2">Use a key to call the same public <code>/v1</code> API the website uses. Interactive OpenAPI docs are at <code>/docs</code>; the machine-readable schema is <code>/openapi.json</code>.</p>
      <p className="m-0 max-w-[70ch] text-[14px] leading-[1.55] text-fg-2">Core endpoints: <code>POST /v1/uploads</code>, <code>POST /v1/clips</code> (and <code>/quote</code>), <code>{`GET /v1/jobs/{id}`}</code>, <code>GET /v1/options</code>, <code>GET /v1/credits</code>, <code>GET|POST /v1/keys</code>. No separate SDK is shipped here.</p>
      <section className="panel" aria-labelledby="keys-title">
        <h2 id="keys-title" className="!mb-0 !text-[16px] font-semibold">API keys</h2>
        {fresh && <p className="notice" role="status">Copy this key now. It won't be shown again.<br /><code>{fresh}</code></p>}
        {keys === null ? <p className="muted">Loading…</p> : !keys.length ? <p className="muted">No keys yet.</p>
          : keys.map((k) => (<p key={k.id} className="key"><code>{k.prefix}…</code> {k.name}
              <button className="link" onClick={() => api(`/v1/keys/${k.id}`, { method: "DELETE" }).then(load).catch(fail)}>Revoke</button></p>))}
        <div><button className="btn small primary" onClick={() => api("/v1/keys", { body: { name: "dashboard" } })
          .then((r) => { setFresh(r.key); load(); }).catch(fail)}>Create a key</button></div>
      </section>
    </>
  );
}
