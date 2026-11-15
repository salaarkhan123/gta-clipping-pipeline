"use client";
import { useState } from "react";
import { api, ApiError, setToken } from "@/lib/api";

// Sign up or log in. One form, one step. Used as a page and as a dialog over the home page.
export function AuthForm({ initial = "signup", onDone, note }: { initial?: "signup" | "login"; onDone: () => void; note?: string }) {
  const [mode, setMode] = useState<"signup" | "login" | "forgot">(initial);
  const [email, setEmail] = useState(""), [password, setPassword] = useState("");
  const [agree, setAgree] = useState(false);
  const [busy, setBusy] = useState(false), [error, setError] = useState(""), [sent, setSent] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(""); setBusy(true);
    try {
      if (mode === "forgot") {
        await api("/v1/auth/forgot", { body: { email }, auth: false });
        setSent(true);
      } else {
        const r = await api(`/v1/auth/${mode}`, { body: { email, password }, auth: false });
        setToken(r.token);
        onDone();
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Try again.");
    } finally { setBusy(false); }
  }

  if (sent) return <p className="auth-note">If that email has an account, a reset link is on its way. It works for one hour.</p>;
  return (
    <form className="auth" onSubmit={submit}>
      <h2>{mode === "signup" ? "Create your account" : mode === "login" ? "Log in" : "Reset your password"}</h2>
      {note && <p className="auth-note">{note}</p>}
      <label>Email<input type="email" required autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} /></label>
      {mode !== "forgot" && (
        <label>Password<input type="password" required minLength={8} autoComplete={mode === "signup" ? "new-password" : "current-password"}
          value={password} onChange={(e) => setPassword(e.target.value)} />
          {mode === "signup" && <small>At least 8 characters.</small>}</label>
      )}
      {mode === "signup" && (
        <label className="check"><input type="checkbox" required checked={agree} onChange={(e) => setAgree(e.target.checked)} />
          <span>I own the videos I upload, or have permission to clip them.</span></label>
      )}
      {error && <p className="error" role="alert">{error}</p>}
      <button className="btn primary" disabled={busy}>
        {busy ? "One moment…" : mode === "signup" ? "Create account" : mode === "login" ? "Log in" : "Send reset link"}
      </button>
      <p className="auth-switch">
        {mode === "signup" ? <>Have an account? <button type="button" onClick={() => setMode("login")}>Log in</button></>
          : mode === "login" ? <><button type="button" onClick={() => setMode("signup")}>Create an account</button>
            <button type="button" onClick={() => setMode("forgot")}>Forgot password</button></>
          : <button type="button" onClick={() => setMode("login")}>Back to log in</button>}
      </p>
    </form>
  );
}

export function AuthDialog({ open, onClose, onDone, note }: { open: boolean; onClose: () => void; onDone: () => void; note?: string }) {
  if (!open) return null;
  return (
    <div className="dialog-wrap" onClick={onClose}>
      <div className="dialog" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
        <button className="dialog-x" aria-label="Close" onClick={onClose}>×</button>
        <AuthForm onDone={onDone} note={note} />
      </div>
    </div>
  );
}
