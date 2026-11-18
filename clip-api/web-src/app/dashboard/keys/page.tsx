"use client";
import { useCallback, useEffect, useState } from "react";
import { Icon } from "@/components/dash/Icon";
import { useDash } from "@/components/dash/Shell";
import { API, api } from "@/lib/api";

export default function Keys() {
  const { fail } = useDash();
  const [keys, setKeys] = useState<any[] | null>(null), [fresh, setFresh] = useState("");
  const load = useCallback(() => api("/v1/keys").then((r) => setKeys(r.keys)).catch(fail), [fail]);
  useEffect(() => { load(); }, [load]);

  return (
    <>
      <h1 className="dash-title">API</h1>
      <p className="muted">Use a key to make clips from your own code. The website uses the same API.</p>
      <div><a className="btn small ghost" href={`${API}/docs`} target="_blank" rel="noreferrer">Read the API docs <Icon name="external" size={16} /></a></div>
      <section className="panel" aria-labelledby="keys-title">
        <h2 id="keys-title">API keys</h2>
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
