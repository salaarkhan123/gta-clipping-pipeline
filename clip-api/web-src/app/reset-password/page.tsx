"use client";
import Link from "next/link";
import { useState } from "react";
import { Nav } from "@/components/Chrome";
import { api, ApiError } from "@/lib/api";

// The same card as the log-in page.
const CARD = "w-[min(100%,420px)] rounded-[24px] border border-solid border-line-soft bg-card p-8 shadow-[0_30px_80px_rgba(0,0,0,.6)] narrow:p-6 [&_.auth_h2]:text-[26px] [&_.auth_h2]:font-semibold [&_.auth_h2]:tracking-[-0.02em] [&_.btn.primary]:w-full [&_input]:rounded-full [&_input]:px-[18px]";

export default function Reset() {
  const [password, setPassword] = useState(""), [done, setDone] = useState(false), [error, setError] = useState("");
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    try {
      await api("/v1/auth/reset", { body: { token: new URLSearchParams(window.location.search).get("token") || "", password }, auth: false });
      setDone(true);
    } catch (err) { setError(err instanceof ApiError ? err.message : "Something went wrong. Try again."); }
  }
  return (
    <div className="grid min-h-screen grid-rows-[auto_1fr]">
      <Nav />
      <main className="grid place-items-center px-4 pb-16 pt-10 [background:radial-gradient(ellipse_at_50%_-10%,rgba(255,255,255,.07),transparent_55%)]">
        <div className={CARD}>
          {done ? <div className="auth"><h2>Password changed</h2><p className="muted">Log in with your new password.</p><Link className="btn primary" href="/login/">Log in</Link></div> : (
            <form className="auth" onSubmit={submit}>
              <h2>Choose a new password</h2>
              <label>New password<input type="password" required minLength={8} autoComplete="new-password" value={password}
                onChange={(e) => setPassword(e.target.value)} /><small>At least 8 characters.</small></label>
              {error && <p className="error" role="alert">{error}</p>}
              <button className="btn primary">Save password</button>
            </form>
          )}
        </div>
      </main>
    </div>
  );
}
