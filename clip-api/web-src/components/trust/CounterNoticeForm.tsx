"use client";
// The reported user's counter-notice: POST /v1/trust/my-cases/{ref}/counter-notice (the CounterNotice model in
// app/routes_trust.py, 17 U.S.C. 512(g)(3)). Every `name` below is a CounterNotice field (tests/test_case_screens.py).
import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import { fieldError, focusSoon } from "@/lib/trust";
import { Err, HINT, INPUT, wire } from "./Field";

type Form = { name: string; address: string; phone: string; explanation: string; mistake: boolean; consent: boolean; signature: string };
type Key = keyof Form;
const ORDER: Key[] = ["name", "address", "phone", "explanation", "mistake", "consent", "signature"];
const EMPTY: Form = { name: "", address: "", phone: "", explanation: "", mistake: false, consent: false, signature: "" };

export const MISTAKE = "I swear, under penalty of perjury, that I have a good faith belief that the material was removed or disabled as a result of mistake or misidentification of the material to be removed or disabled.";
export const CONSENT = "I consent to the jurisdiction of the Federal District Court for the judicial district in which my address is located or, if my address is outside the United States, for any judicial district in which ClutchClips may be found, and I will accept service of process from the person who sent the notice, or an agent of that person.";

function check(f: Form): Partial<Record<Key, string>> {
  const e: Partial<Record<Key, string>> = {};
  const size = (k: Key, min: number, max: number, what: string) => {
    const n = String(f[k]).trim().length;
    if (n < min) e[k] = `Enter ${what} (at least ${min} characters).`;
    else if (n > max) e[k] = `Keep this to ${max} characters or fewer.`;
  };
  size("name", 2, 200, "your full name");
  size("address", 5, 500, "your postal address");
  size("phone", 5, 40, "your phone number");
  size("explanation", 10, 5000, "why the content was taken down by mistake");
  if (!f.mistake) e.mistake = "Tick this statement to send a counter-notice.";
  if (!f.consent) e.consent = "Tick this statement to send a counter-notice.";
  size("signature", 2, 200, "your full name as your signature");
  return e;
}

export function CounterNoticeForm({ reference, onSent }: { reference: string; onSent: (c: any) => void }) {
  const [f, setF] = useState<Form>(EMPTY);
  const [errors, setErrors] = useState<Partial<Record<Key, string>>>({});
  const [problem, setProblem] = useState(""), [busy, setBusy] = useState(false);
  const set = <K extends Key>(k: K, v: Form[K]) => setF((x) => ({ ...x, [k]: v }));

  function show(e: Partial<Record<Key, string>>) {
    setErrors(e);
    const first = ORDER.find((k) => e[k]);
    if (first) focusSoon(`cn-${first}`);
  }

  async function submit(ev: React.FormEvent) {
    ev.preventDefault();
    setProblem("");
    const e = check(f);
    if (Object.keys(e).length) return show(e);
    setBusy(true);
    try {
      const body = { ...f, name: f.name.trim(), address: f.address.trim(), phone: f.phone.trim(), explanation: f.explanation.trim(), signature: f.signature.trim() };
      onSent(await api(`/v1/trust/my-cases/${encodeURIComponent(reference)}/counter-notice`, { body }));
    } catch (err) {
      const { field, text } = err instanceof ApiError && err.status === 422 ? fieldError(err.message, ORDER) : { field: null, text: err instanceof Error ? err.message : "Something went wrong." };
      if (field) return show({ [field]: text });
      setProblem(text);
      focusSoon("cn-problem");
    } finally { setBusy(false); }
  }

  const field = (k: Key, label: string, input: React.ReactNode, hint?: string) => (
    <div className="grid gap-[6px]">
      <label htmlFor={`cn-${k}`}>{label}</label>
      {input}
      {hint && <span id={`cn-${k}-hint`} className={HINT}>{hint}</span>}
      <Err id={`cn-${k}`} text={errors[k]} />
    </div>
  );
  const box = (k: "mistake" | "consent", input: React.ReactNode, label: string) => (
    <div className="grid gap-[6px]">
      <label className="check items-start" htmlFor={`cn-${k}`}>{input}<span>{label}</span></label>
      <Err id={`cn-${k}`} text={errors[k]} />
    </div>
  );

  return (
    <form className="grid gap-4" onSubmit={submit} noValidate aria-labelledby="cn-title" aria-describedby="cn-about">
      <h3 id="cn-title" className="text-[18px]">Send a counter-notice</h3>
      <div id="cn-about" className="grid gap-2 text-[14px] text-soft">
        <p>Send this only if you believe your content was taken down by mistake, for example because you own it, have permission, or it was misidentified.</p>
        <p><strong>A copy of this counter-notice, with your name, address and phone number, goes to the person who reported your content.</strong> The law requires it.</p>
        <p>Unless they tell us within 10 business days that they have filed a court action, an admin may restore your content, if its files still exist. Nothing is restored automatically.</p>
      </div>
      {field("name", "Full name (required)", <input className={INPUT} type="text" name="name" autoComplete="name" value={f.name}
        onChange={(e) => set("name", e.target.value)} {...wire("cn-name", errors.name)} />)}
      {field("address", "Postal address (required)", <textarea className={INPUT} name="address" rows={2} autoComplete="street-address" value={f.address}
        onChange={(e) => set("address", e.target.value)} {...wire("cn-address", errors.address)} />)}
      {field("phone", "Phone (required)", <input className={INPUT} type="tel" name="phone" autoComplete="tel" value={f.phone}
        onChange={(e) => set("phone", e.target.value)} {...wire("cn-phone", errors.phone)} />)}
      {field("explanation", "Why it was a mistake (required)", <textarea className={INPUT} name="explanation" rows={4} value={f.explanation}
        onChange={(e) => set("explanation", e.target.value)} {...wire("cn-explanation", errors.explanation, true)} />,
        "Say which content it is and why it was removed or disabled by mistake or misidentification.")}
      {box("mistake", <input type="checkbox" name="mistake" className="mt-[3px] flex-none" checked={f.mistake}
        onChange={(e) => set("mistake", e.target.checked)} {...wire("cn-mistake", errors.mistake)} />, MISTAKE)}
      {box("consent", <input type="checkbox" name="consent" className="mt-[3px] flex-none" checked={f.consent}
        onChange={(e) => set("consent", e.target.checked)} {...wire("cn-consent", errors.consent)} />, CONSENT)}
      {field("signature", "Signature: type your full name (required)", <input className={INPUT} type="text" name="signature" autoComplete="name"
        value={f.signature} onChange={(e) => set("signature", e.target.value)} {...wire("cn-signature", errors.signature, true)} />,
        "Typing your name here signs this counter-notice.")}
      {problem && <p id="cn-problem" className="error" role="alert" tabIndex={-1}>{problem}</p>}
      <div><button className="btn primary" disabled={busy}>{busy ? "Sending…" : "Send counter-notice"}</button></div>
    </form>
  );
}
