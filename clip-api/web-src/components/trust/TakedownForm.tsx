"use client";
// The public report form: POST /v1/trust/reports (the Report model in app/routes_trust.py). No login, no CAPTCHA.
// Every `name` below is a Report field (tests/test_case_screens.py checks it). The checks here mirror the API's so
// most mistakes are caught before sending; the API's own 422 is still shown next to the field it names.
import Link from "next/link";
import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import { fieldError, focusSoon } from "@/lib/trust";
import { Err, HINT, INPUT, LINK, wire } from "./Field";

type Kind = "copyright" | "likeness";
type Form = {
  kind: Kind; name: string; email: string; organization: string; address: string; phone: string; relationship: string;
  work: string; reported_urls: string; details: string; good_faith: boolean; accurate: boolean; signature: string; website: string;
};
type Key = Exclude<keyof Form, "website">;
// The order errors are checked in, so focus goes to the first one on the page.
const ORDER: Key[] = ["kind", "name", "email", "organization", "address", "phone", "relationship", "work", "reported_urls",
  "details", "good_faith", "accurate", "signature"];
const EMPTY: Form = { kind: "copyright", name: "", email: "", organization: "", address: "", phone: "", relationship: "",
  work: "", reported_urls: "", details: "", good_faith: false, accurate: false, signature: "", website: "" };
const MAX_URLS = 20, MAX_BODY = 32 * 1024;

const RELATIONSHIPS: Record<Kind, [string, string][]> = {
  copyright: [["owner", "I own the copyright"], ["agent", "I am authorised to act for the copyright owner"]],
  likeness: [["self", "I am the person shown"], ["representative", "I represent the person shown (for example as their parent, guardian, agent or lawyer)"]],
};
const GOOD_FAITH: Record<Kind, string> = {
  copyright: "I believe in good faith that the use of the material I reported is not authorised by the copyright owner, its agent or the law.",
  likeness: "I believe in good faith that the use of the material I reported is not authorised by the person shown, their representative or the law.",
};
const ACCURATE: Record<Kind, string> = {
  copyright: "Under penalty of perjury, I state that the information in this notice is accurate and that I am the copyright owner or am authorised to act on the owner's behalf.",
  likeness: "Under penalty of perjury, I state that the information in this report is accurate and that I am the person shown or am authorised to act on their behalf.",
};

const lines = (s: string) => s.split("\n").map((x) => x.trim()).filter(Boolean);

function check(f: Form): Partial<Record<Key, string>> {
  const e: Partial<Record<Key, string>> = {};
  const size = (k: Key, min: number, max: number, what: string) => {
    const n = String(f[k]).trim().length;
    if (n < min) e[k] = min <= 1 ? `Enter ${what}.` : `Enter ${what} (at least ${min} characters).`;
    else if (n > max) e[k] = `Keep this to ${max} characters or fewer.`;
  };
  size("name", 2, 200, "your full name");
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(f.email.trim())) e.email = "Enter an email address we can reply to.";
  size("organization", 0, 200, "");
  if (f.kind === "copyright") size("address", 1, 500, "your postal address (a copyright notice needs one)");
  else size("address", 0, 500, "");
  size("phone", 0, 40, "");
  if (!RELATIONSHIPS[f.kind].some(([v]) => v === f.relationship)) e.relationship = "Choose who you are.";
  size("work", 10, 5000, f.kind === "copyright" ? "the work you own" : "who is shown and how");
  const urls = lines(f.reported_urls);
  if (!urls.length) e.reported_urls = "Add at least one link.";
  else if (urls.length > MAX_URLS) e.reported_urls = `Add at most ${MAX_URLS} links (you added ${urls.length}). Send another report for the rest.`;
  else {
    const bad = urls.findIndex((u) => u.length < 4 || u.length > 2000);
    if (bad >= 0) e.reported_urls = `Line ${bad + 1} is not a link (4 to 2000 characters).`;
  }
  size("details", 0, 5000, "");
  if (!f.good_faith) e.good_faith = "Tick this statement to send the report.";
  if (!f.accurate) e.accurate = "Tick this statement to send the report.";
  size("signature", 2, 200, "your full name as your signature");
  return e;
}

export function TakedownForm() {
  const [f, setF] = useState<Form>(EMPTY);
  const [errors, setErrors] = useState<Partial<Record<Key, string>>>({});
  const [problem, setProblem] = useState(""), [busy, setBusy] = useState(false);
  const [done, setDone] = useState<{ reference: string; email: string } | null>(null);
  const set = <K extends keyof Form>(k: K, v: Form[K]) => setF((x) => ({ ...x, [k]: v }));
  const kind = f.kind;

  function show(e: Partial<Record<Key, string>>) {
    setErrors(e);
    const first = ORDER.find((k) => e[k]);
    if (first) focusSoon(`tk-${first}`);
  }

  async function submit(ev: React.FormEvent) {
    ev.preventDefault();
    setProblem("");
    const e = check(f);
    if (Object.keys(e).length) return show(e);
    const opt = (s: string) => s.trim() || null;
    const body = { kind, name: f.name.trim(), email: f.email.trim(), organization: opt(f.organization), address: opt(f.address),
      phone: opt(f.phone), relationship: f.relationship, work: f.work.trim(), reported_urls: lines(f.reported_urls),
      details: opt(f.details), good_faith: f.good_faith, accurate: f.accurate, signature: f.signature.trim(), website: f.website };
    if (new Blob([JSON.stringify(body)]).size > MAX_BODY) {
      setProblem("The report is too large (32 KB at most). Shorten the details, or send the rest in a second report.");
      return focusSoon("tk-problem");
    }
    setBusy(true);
    try {
      const r = await api<{ reference: string }>("/v1/trust/reports", { body, auth: false });
      setDone({ reference: r.reference, email: body.email });
      setErrors({});
      setF(EMPTY);
      focusSoon("tk-done");
    } catch (err) {
      if (err instanceof ApiError && err.status === 422) {
        const { field, text } = fieldError(err.message, ORDER);
        if (field) return show({ [field]: text });
        setProblem(text);
      } else if (err instanceof ApiError && err.status === 429) {
        setProblem("Too many reports were sent from here in a short time. Wait an hour and try again; if you have sent 3 reports from this email today, wait until tomorrow. "
          + "We accept 5 reports an hour and 20 a day from one connection, and 3 a day from one email address. If it cannot wait, email support@clutchclips.io.");
      } else setProblem(err instanceof Error ? err.message : "Something went wrong. Try again.");
      focusSoon("tk-problem");
    } finally { setBusy(false); }
  }

  if (done) return (
    <section className="panel" aria-labelledby="tk-done">
      <h2 id="tk-done" tabIndex={-1} className="text-[24px] focus:outline-none">Report received</h2>
      <p>Your case reference is <strong className="font-display text-[20px] tracking-[.04em] text-lime">{done.reference}</strong>. Quote it in any email about this report.</p>
      <p className="muted">We emailed a copy to {done.email}. A person at ClutchClips reviews every report. Nothing is removed automatically: we check the report and may ask you for more information.</p>
      <div><button type="button" className="btn small ghost" onClick={() => { setDone(null); focusSoon("tk-kind"); }}>Send another report</button></div>
    </section>
  );

  const field = (k: Key, label: string, input: React.ReactNode, hint?: string) => (
    <div className="grid gap-[6px]">
      <label htmlFor={`tk-${k}`}>{label}</label>
      {input}
      {hint && <span id={`tk-${k}-hint`} className={HINT}>{hint}</span>}
      <Err id={`tk-${k}`} text={errors[k]} />
    </div>
  );
  const box = (k: "good_faith" | "accurate", input: React.ReactNode, label: string) => (
    <div className="grid gap-[6px]">
      <label className="check items-start" htmlFor={`tk-${k}`}>{input}<span>{label}</span></label>
      <Err id={`tk-${k}`} text={errors[k]} />
    </div>
  );

  return (
    <form className="panel" onSubmit={submit} noValidate aria-describedby="tk-intro">
      <p id="tk-intro" className="muted small">Every field marked “required” must be filled in. A person reviews every report; nothing is removed automatically.</p>

      <fieldset className="grid gap-[10px] border-0" aria-describedby={errors.kind ? "tk-kind-err" : undefined}>
        <legend className="mb-2 font-display text-[18px] font-semibold">What are you reporting? (required)</legend>
        {(["copyright", "likeness"] as Kind[]).map((k) => (
          <label key={k} className="check items-start rounded-12 border border-solid border-line p-3 has-[:checked]:border-lime">
            <input type="radio" name="kind" value={k} id={k === "copyright" ? "tk-kind" : undefined} className="mt-[3px] flex-none"
              checked={kind === k} onChange={() => setF((x) => ({ ...x, kind: k, relationship: "" }))} />
            <span className="grid gap-[2px]"><b>{k === "copyright" ? "Copyright notice" : "Likeness report"}</b>
              <span className={HINT}>{k === "copyright" ? "Content on ClutchClips copies a work you own, such as a video, stream, music or artwork."
                : "Content on ClutchClips shows you (your face, voice or name) without your permission."}</span></span>
          </label>))}
        <Err id="tk-kind" text={errors.kind} />
      </fieldset>

      <fieldset className="grid gap-4 border-0">
        <legend className="mb-2 font-display text-[18px] font-semibold">Your details</legend>
        {field("name", "Full name (required)", <input className={INPUT} type="text" name="name" autoComplete="name" value={f.name}
          onChange={(e) => set("name", e.target.value)} {...wire("tk-name", errors.name)} />)}
        {field("email", "Email (required)", <input className={INPUT} type="email" name="email" autoComplete="email" value={f.email}
          onChange={(e) => set("email", e.target.value)} {...wire("tk-email", errors.email, true)} />, "We send the case reference here.")}
        {field("organization", "Organisation (optional)", <input className={INPUT} type="text" name="organization" autoComplete="organization" value={f.organization}
          onChange={(e) => set("organization", e.target.value)} {...wire("tk-organization", errors.organization)} />)}
        {field("address", kind === "copyright" ? "Postal address (required)" : "Postal address (optional)", <textarea className={INPUT} name="address" rows={2}
          autoComplete="street-address" value={f.address} onChange={(e) => set("address", e.target.value)} {...wire("tk-address", errors.address, true)} />,
          kind === "copyright" ? "The law asks for it in a copyright notice. The account holder does not see it." : "Only if you want us to write to you by post.")}
        {field("phone", "Phone (optional)", <input className={INPUT} type="tel" name="phone" autoComplete="tel" value={f.phone}
          onChange={(e) => set("phone", e.target.value)} {...wire("tk-phone", errors.phone)} />)}
      </fieldset>

      <fieldset className="grid gap-[10px] border-0" aria-describedby={errors.relationship ? "tk-relationship-err" : undefined}>
        <legend className="mb-2 font-display text-[18px] font-semibold">Who are you? (required)</legend>
        {RELATIONSHIPS[kind].map(([v, text], i) => (
          <label key={v} className="check items-start">
            <input type="radio" name="relationship" value={v} id={i === 0 ? "tk-relationship" : undefined} className="mt-[3px] flex-none"
              checked={f.relationship === v} onChange={() => set("relationship", v)} aria-invalid={errors.relationship ? true : undefined} />
            <span>{text}</span>
          </label>))}
        <Err id="tk-relationship" text={errors.relationship} />
      </fieldset>

      <fieldset className="grid gap-4 border-0">
        <legend className="mb-2 font-display text-[18px] font-semibold">What is being used</legend>
        {field("work", kind === "copyright" ? "The work you own (required)" : "The person shown, and how (required)",
          <textarea className={INPUT} name="work" rows={4} value={f.work} onChange={(e) => set("work", e.target.value)} {...wire("tk-work", errors.work, true)} />,
          kind === "copyright" ? "Name the work and where the original is, for example the title and a link to your channel or store page."
            : "Say who is shown and how they appear, for example your face on a facecam, your voice or your name.")}
        {field("reported_urls", `Links to the content on ClutchClips (required, up to ${MAX_URLS}, one per line)`,
          <textarea className={INPUT} name="reported_urls" rows={4} spellCheck={false} value={f.reported_urls}
            onChange={(e) => set("reported_urls", e.target.value)} {...wire("tk-reported_urls", errors.reported_urls, true)} />,
          `${lines(f.reported_urls).length} of ${MAX_URLS} links. A link to the clip or video, or its id (it starts with clip_, upl_ or job_).`)}
        {field("details", "Anything else we should know (optional)", <textarea className={INPUT} name="details" rows={3} value={f.details}
          onChange={(e) => set("details", e.target.value)} {...wire("tk-details", errors.details)} />)}
      </fieldset>

      <fieldset className="grid gap-4 border-0">
        <legend className="mb-2 font-display text-[18px] font-semibold">Statements (required)</legend>
        {box("good_faith", <input type="checkbox" name="good_faith" className="mt-[3px] flex-none" checked={f.good_faith}
          onChange={(e) => set("good_faith", e.target.checked)} {...wire("tk-good_faith", errors.good_faith)} />, GOOD_FAITH[kind])}
        {box("accurate", <input type="checkbox" name="accurate" className="mt-[3px] flex-none" checked={f.accurate}
          onChange={(e) => set("accurate", e.target.checked)} {...wire("tk-accurate", errors.accurate)} />, ACCURATE[kind])}
        {field("signature", "Signature: type your full name (required)", <input className={INPUT} type="text" name="signature" autoComplete="name"
          value={f.signature} onChange={(e) => set("signature", e.target.value)} {...wire("tk-signature", errors.signature, true)} />,
          "Typing your name here signs this report.")}
      </fieldset>

      {/* Spam trap: people never see or fill it. A report that fills it is answered like any other and not kept. */}
      <div className="absolute -left-[10000px] top-auto h-px w-px overflow-hidden" aria-hidden="true">
        <label htmlFor="tk-website">Website</label>
        <input id="tk-website" type="text" name="website" tabIndex={-1} autoComplete="off" aria-hidden="true" value={f.website}
          onChange={(e) => set("website", e.target.value)} />
      </div>

      <p className={HINT}>The account holder sees your name or organisation and the work you named,
        never your email, address or phone. Read the <Link className={LINK} href="/terms/">Terms</Link>, the <Link className={LINK} href="/privacy/">Privacy Policy</Link>
        {" "}and the <Link className={LINK} href="/copyright/">Copyright policy</Link>.</p>
      {problem && <p id="tk-problem" className="error" role="alert" tabIndex={-1}>{problem}</p>}
      <div><button className="btn primary" disabled={busy}>{busy ? "Sending…" : "Send report"}</button></div>
    </form>
  );
}
