// The shared layout of the legal pages: title, version and effective date (lib/legal.ts, the same as
// GET /v1/legal/policies), the draft notice, a table of contents and the sections.
import Link from "next/link";
import { Footer, Nav } from "@/components/Chrome";
import { CONTACT, POLICIES, policy } from "@/lib/legal";

export type Section = { id: string; title: string; body: React.ReactNode };

const MARK = "rounded-[4px] bg-[rgba(255,182,72,.16)] px-1 font-semibold text-warn [box-decoration-break:clone]";

// A fact only the owner knows. Visible on purpose: the page is not final while one is left.
export function Owner({ children }: { children: React.ReactNode }) {
  return <mark className={MARK} data-owner-placeholder="">[OWNER: {children}]</mark>;
}

// A rule the owner has to decide. The text after it is the proposal.
export function Decision({ children }: { children?: React.ReactNode }) {
  return <mark className={MARK} data-owner-placeholder="">[OWNER DECISION{children ? <>: {children}</> : null}]</mark>;
}

// A rule the owner has set that a lawyer still has to check.
export function Review() {
  return <mark className={MARK}>[Subject to legal review]</mark>;
}

// A compliance step that is known and not done yet.
export function Outstanding({ children }: { children: React.ReactNode }) {
  return <mark className={MARK}>[OUTSTANDING: {children}]</mark>;
}

// An email address from CONTACT, as a link.
export function Mail({ to, subject }: { to: string; subject?: string }) {
  return <a href={`mailto:${to}${subject ? `?subject=${encodeURIComponent(subject)}` : ""}`}>{to}</a>;
}

export const date = (iso: string) =>
  new Date(`${iso}T00:00:00Z`).toLocaleDateString("en-CA", { year: "numeric", month: "long", day: "numeric", timeZone: "UTC" });

// A link to an outside site, opened in a new tab.
export function Ext({ href, children }: { href: string; children: React.ReactNode }) {
  return <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>;
}

// Prose: the site reset removes margins and list padding, so the page sets its own.
const PROSE = "text-[16px] leading-[1.7] text-soft [overflow-wrap:anywhere] "
  + "[&_p]:mb-4 [&_ul]:mb-4 [&_ul]:list-disc [&_ul]:pl-6 [&_ol]:mb-4 [&_ol]:list-decimal [&_ol]:pl-6 [&_li]:mb-2 "
  + "[&_h3]:mb-3 [&_h3]:mt-7 [&_h3]:text-[18px] [&_h3]:text-text "
  + "[&_a]:text-lime [&_a]:underline [&_a]:underline-offset-2 [&_strong]:text-text "
  + "[&_table]:mb-4 [&_table]:w-full [&_table]:border-collapse [&_table]:text-[14px] "
  + "[&_th]:border-0 [&_th]:border-b [&_th]:border-solid [&_th]:border-line [&_th]:px-3 [&_th]:py-2 [&_th]:text-left [&_th]:align-bottom [&_th]:text-text "
  + "[&_td]:border-0 [&_td]:border-b [&_td]:border-solid [&_td]:border-line-soft [&_td]:px-3 [&_td]:py-2 [&_td]:align-top";

// Tables scroll inside their own box on a phone; the page never scrolls sideways.
export function Table({ head, rows }: { head: string[]; rows: React.ReactNode[][] }) {
  return (
    <div className="mb-4 max-w-full overflow-x-auto rounded-12 border border-solid border-line">
      <table className="min-w-[560px] [&_tr:last-child_td]:border-b-0">
        <thead><tr>{head.map((h) => <th key={h} scope="col">{h}</th>)}</tr></thead>
        <tbody>{rows.map((r, i) => <tr key={i}>{r.map((c, j) => <td key={j}>{c}</td>)}</tr>)}</tbody>
      </table>
    </div>
  );
}

// The drafts render only in a preview build (LEGAL_PREVIEW=1, read at build time). A production build shows a short
// stub instead, so a page with an [OWNER …] placeholder is never deployed; scripts/check-legal.mjs enforces it.
export const PREVIEW = process.env.LEGAL_PREVIEW === "1";

// Who answers while a page is a stub: the address the owner set for that subject (CONTACT in lib/legal.ts).
const STUB_CONTACT: Record<string, string> = { copyright: CONTACT.copyright, terms: CONTACT.support, refunds: CONTACT.support,
  "acceptable-use": CONTACT.support };

function Stub({ id, title }: { id: string; title: string }) {
  const to = STUB_CONTACT[id] || CONTACT.privacy;
  return (
    <>
      <Nav />
      <main>
        <header className="page-head">
          <div className="container">
            <span className="pill"><span className="dot" />LEGAL</span>
            <h1>{title}</h1>
            <p>This policy is being finalised. Contact <a className="text-lime underline" href={`mailto:${to}`}>{to}</a>.
              {id === "copyright" && <> To report content on ClutchClips, use the <Link className="text-lime underline" href="/takedown/">report form</Link>.</>}</p>
          </div>
        </header>
      </main>
      <Footer />
    </>
  );
}

export function LegalPage({ id, intro, sections }: { id: string; intro: React.ReactNode; sections: Section[] }) {
  const p = policy(id);
  if (!PREVIEW) return <Stub id={id} title={p.title} />;
  return (
    <>
      <Nav />
      <main>
        <header className="page-head pb-8">
          <div className="container">
            <span className="pill"><span className="dot" />LEGAL</span>
            <h1>{p.title}</h1>
            <p>Version {p.version} · Effective {date(p.effective)}</p>
          </div>
        </header>
        <div className="container mx-auto max-w-[1040px]">
          <p role="note" className="mb-8 rounded-12 border border-solid border-warn bg-[rgba(255,182,72,.08)] px-4 py-3 text-[15px] text-text narrow:mb-6">
            <strong className="text-warn">Draft: pending legal review.</strong> This page is a draft for review by a lawyer and is not legal advice.
          </p>
        </div>
        <div className="container mx-auto grid max-w-[1040px] grid-cols-[220px_minmax(0,1fr)] items-start gap-12 pb-16 narrow:grid-cols-1 narrow:gap-6">
          <nav aria-label="On this page" className="sticky top-[96px] rounded-16 border border-solid border-line bg-panel p-5 narrow:static">
            <h2 className="mb-3 font-body text-[13px] font-semibold uppercase tracking-[.12em] text-muted">On this page</h2>
            <ol className="grid list-none gap-2 text-[14px]">
              {sections.map((s) => <li key={s.id}><a href={`#${s.id}`} className="text-label hover:text-lime">{s.title}</a></li>)}
            </ol>
          </nav>
          <article className={`min-w-0 ${PROSE}`}>
            <div className="mb-8 text-[17px] text-text">{intro}</div>
            {sections.map((s) => (
              <section key={s.id} id={s.id} aria-labelledby={`${s.id}-h`} className="scroll-mt-[96px] border-0 border-t border-solid border-line-soft py-8">
                <h2 id={`${s.id}-h`} className="mb-4 text-[24px] text-text">{s.title}</h2>
                {s.body}
              </section>
            ))}
            <section aria-labelledby="other-h" className="border-0 border-t border-solid border-line-soft py-8">
              <h2 id="other-h" className="mb-4 text-[24px] text-text">Our other policies</h2>
              <ul>{POLICIES.filter((x) => x.id !== id).map((x) => <li key={x.id}><Link href={x.path}>{x.title}</Link></li>)}</ul>
            </section>
          </article>
        </div>
      </main>
      <Footer />
    </>
  );
}
