"use client";
import Link from "next/link";
import { useState } from "react";
import { Nav } from "@/components/Chrome";
import { api, ApiError } from "@/lib/api";

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
    <>
      <Nav />
      <main className="narrow">
        {done ? <div className="auth"><h2>Password changed</h2><Link className="btn primary" href="/login/">Log in</Link></div> : (
          <form className="auth" onSubmit={submit}>
            <h2>Choose a new password</h2>
            <label>New password<input type="password" required minLength={8} autoComplete="new-password" value={password}
              onChange={(e) => setPassword(e.target.value)} /><small>At least 8 characters.</small></label>
            {error && <p className="error" role="alert">{error}</p>}
            <button className="btn primary">Save password</button>
          </form>
        )}
      </main>
    </>
  );
}
