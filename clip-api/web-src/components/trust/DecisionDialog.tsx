"use client";
// The confirm dialog for one admin decision. A native modal <dialog>: the page behind it is inert, so focus stays
// inside, and Escape closes it. A destructive decision (`danger` set) asks a second time, naming what will happen.
import { useEffect, useRef, useState } from "react";
import { focusSoon } from "@/lib/trust";
import { Err, HINT, INPUT, wire } from "./Field";

export type DecisionBody = { note?: string; message?: string; account_id?: string };
type Owner = { id: string; email: string | null };

export function DecisionDialog({ label, what, message, owners, danger, onConfirm, onClose }: {
  label: string; what: string;
  message?: "required" | "optional";            // request_info, reject: words emailed to the claimant
  owners?: Owner[];                             // terminate: whose account to suspend; the note is required too
  danger?: (accountId: string) => string;       // remove, delete_content, terminate: the second confirm's words
  onConfirm: (body: DecisionBody) => Promise<void>; onClose: () => void;
}) {
  const box = useRef<HTMLDialogElement>(null);
  const [note, setNote] = useState(""), [msg, setMsg] = useState("");
  const [account, setAccount] = useState(owners?.length === 1 ? owners[0].id : "");
  const [sure, setSure] = useState(false), [busy, setBusy] = useState(false), [problem, setProblem] = useState("");
  const [errors, setErrors] = useState<{ note?: string; message?: string; account_id?: string }>({});
  const terminate = !!owners;
  const first = terminate ? "dd-account_id" : message ? "dd-message" : "dd-note";
  useEffect(() => { if (box.current && !box.current.open) box.current.showModal(); focusSoon(first); }, []);   // eslint-disable-line react-hooks/exhaustive-deps

  async function send() {
    setBusy(true); setProblem("");
    try {
      await onConfirm({ note: note.trim() || undefined, message: message ? msg.trim() || undefined : undefined, account_id: terminate ? account : undefined });
      box.current?.close();
    } catch (e) {
      setSure(false);
      setProblem(e instanceof Error ? e.message : "Something went wrong.");
      focusSoon("dd-problem");
    } finally { setBusy(false); }
  }

  // A modal dialog makes the page inert, but Tab can still leave for the browser's own controls: wrap it around.
  function trap(e: React.KeyboardEvent) {
    if (e.key !== "Tab" || !box.current) return;
    const all = Array.from(box.current.querySelectorAll<HTMLElement>("button:not([disabled]), select, textarea, input"));
    const at = all.indexOf(document.activeElement as HTMLElement);
    if (e.shiftKey && at <= 0) { e.preventDefault(); all[all.length - 1]?.focus(); }
    else if (!e.shiftKey && at === all.length - 1) { e.preventDefault(); all[0]?.focus(); }
  }

  function submit(ev: React.FormEvent) {
    ev.preventDefault();
    const e: typeof errors = {};
    if (message === "required" && !msg.trim()) e.message = "Write the message the claimant will get.";
    if (terminate && !account) e.account_id = "Choose the account to suspend.";
    if (terminate && !note.trim()) e.note = "Say why this violation is serious enough to suspend the account at once.";
    setErrors(e);
    const bad = (["account_id", "message", "note"] as const).find((k) => e[k]);
    if (bad) return focusSoon(`dd-${bad}`);
    if (danger && !sure) { setSure(true); return focusSoon("dd-sure"); }
    send();
  }

  return (
    <dialog ref={box} className="picker" aria-labelledby="dd-title" onClose={onClose} onKeyDown={trap}>
      <form className="picker-body" onSubmit={submit} noValidate>
        <div className="picker-head"><h2 id="dd-title">{label}</h2>
          <button type="button" className="icon-btn" aria-label="Close" onClick={() => box.current?.close()}>×</button></div>
        {sure && danger ? <>
          <div id="dd-sure" tabIndex={-1} role="alert" className="error grid gap-2">
            <p><strong>Are you sure?</strong></p><p>{danger(account)}</p>
          </div>
          <div className="row">
            <button type="submit" className="btn small primary !bg-danger ![background-image:none] !shadow-none" disabled={busy}>{busy ? "One moment…" : `Yes, ${label.toLowerCase()}`}</button>
            <button type="button" className="btn small ghost" onClick={() => { setSure(false); focusSoon(first); }}>Go back</button>
          </div>
        </> : <>
          <p className="text-[14px] text-soft">{what}</p>
          {terminate && <div className="grid gap-[6px]">
            <label htmlFor="dd-account_id">Account to suspend (required)</label>
            <select name="account_id" className={INPUT} value={account} onChange={(e) => setAccount(e.target.value)}
              {...wire("dd-account_id", errors.account_id)}>
              <option value="">Choose an account</option>
              {owners!.map((o) => <option key={o.id} value={o.id}>{o.email || "(no email)"} · {o.id}</option>)}
            </select>
            <Err id="dd-account_id" text={errors.account_id} />
          </div>}
          {message && <div className="grid gap-[6px]">
            <label htmlFor="dd-message">Message to the claimant ({message})</label>
            <textarea name="message" className={INPUT} rows={4} maxLength={5000} value={msg} onChange={(e) => setMsg(e.target.value)}
              {...wire("dd-message", errors.message, true)} />
            <span id="dd-message-hint" className={HINT}>Emailed to the claimant with the case reference.</span>
            <Err id="dd-message" text={errors.message} />
          </div>}
          <div className="grid gap-[6px]">
            <label htmlFor="dd-note">Note for the case history ({terminate ? "required" : "optional"})</label>
            <textarea name="note" className={INPUT} rows={3} maxLength={5000} value={note} onChange={(e) => setNote(e.target.value)}
              {...wire("dd-note", errors.note, true)} />
            <span id="dd-note-hint" className={HINT}>Only admins see it.</span>
            <Err id="dd-note" text={errors.note} />
          </div>
          {problem && <p id="dd-problem" className="error" role="alert" tabIndex={-1}>{problem}</p>}
          <div className="row">
            <button type="submit" className="btn small primary" disabled={busy}>{busy ? "One moment…" : danger ? "Continue" : label}</button>
            <button type="button" className="btn small ghost" onClick={() => box.current?.close()}>Cancel</button>
          </div>
        </>}
      </form>
    </dialog>
  );
}
