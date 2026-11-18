"use client";
// Plan cards, shared by the public pricing page and the in-app one. Everything shown comes from the server's
// plan config (GET /v1/billing/plans); nothing about price or credits is set here. Styles: app/app-shell.css.
import { FREE_CREDITS, money } from "@/lib/api";
import { Icon } from "./dash/Icon";

export type Plan = { id: string; name: string; price_month_cents: number; price_year_cents: number; monthly_credits: number;
  max_side: number; max_render_min: number | null };

const BLURB: Record<string, string> = {
  free: "Try AI clipping on your own streams, no card needed.",
  starter: "For new clippers building their first accounts.",
  pro: "For serious clippers running campaigns.",
};
const blurb = (p: Plan) => BLURB[p.id] || "For clipping agencies and teams.";
export const INCLUDED = ["AI clip finder and virality score", "Find any moment by speech or what's on screen", "Automatic facecam detection",
  "9:16, 4:5, 1:1 and 16:9", "Caption styles, SRT and VTT export", "AI titles and hashtags", "API access and the agent skill"];
const perJob = (min: number | null) => (min ? `up to ${min >= 60 ? `${min / 60} hr` : `${min} min`}` : "any length");

// The real yearly saving, worked out from the plans the server returns. 0 when there is none.
export function yearlySaving(plans: Plan[]): number {
  const paid = plans.filter((p) => p.price_month_cents > 0);
  return paid.length ? Math.round(100 * (1 - Math.min(...paid.map((p) => p.price_year_cents / (p.price_month_cents * 12))))) : 0;
}

export function PeriodToggle({ yearly, onChange, save }: { yearly: boolean; onChange: (yearly: boolean) => void; save: number }) {
  return (
    <div className="period" role="group" aria-label="Billing period">
      <button type="button" aria-pressed={!yearly} onClick={() => onChange(false)}>Monthly</button>
      <button type="button" aria-pressed={yearly} onClick={() => onChange(true)}>Yearly{save > 0 && <span className="save">Save {save}%</span>}</button>
    </div>
  );
}

// `onPick(plan)` starts checkout for a paid plan; the free plan links to `freeHref`.
export function PlanCards({ plans, currency, yearly, current, busy, onPick, freeHref }: { plans: Plan[]; currency: string; yearly: boolean;
  current: string | null; busy: string; onPick: (p: Plan) => void; freeHref: string }) {
  const paid = plans.filter((p) => p.price_month_cents > 0);
  const popular = paid.length >= 2 ? paid[1].id : paid[0]?.id;
  const fmt = (c: number) => money(c, currency).replace(/\.00$/, "");
  return (
    <div className={`plans ${popular ? "has-popular" : ""}`}>
      {plans.map((p) => {
        const isPaid = p.price_month_cents > 0, pop = p.id === popular;
        const perMonth = yearly ? p.price_year_cents / 12 : p.price_month_cents;
        return (
          <article key={p.id} className={`plan-card ${pop ? "popular" : ""}`} aria-label={`${p.name} plan`}>
            {pop && <p className="plan-flag">Most popular</p>}
            <h3>{p.name}</h3>
            <p className="desc">{blurb(p)}</p>
            <div className="plan-price">
              {isPaid && yearly && perMonth < p.price_month_cents && <s aria-label={`was ${fmt(p.price_month_cents)}`}>{fmt(p.price_month_cents)}</s>}
              <b>{fmt(Math.round(perMonth))}</b><small>/ month</small>
            </div>
            <p className="billed">{!isPaid ? "Free forever" : yearly ? `Billed ${fmt(p.price_year_cents)} yearly` : "Billed monthly"}</p>
            {current === p.id ? <button className="btn ghost" disabled>Your plan</button>
              : isPaid ? <button className={`btn ${pop ? "primary" : "ghost"}`} disabled={busy === p.id} onClick={() => onPick(p)}>
                  {busy === p.id ? "Opening checkout…" : `Get ${p.name}`}</button>
              : <a className="btn ghost" href={freeHref}>Start free</a>}
            <p className="plan-credits"><Icon name="bolt" size={18} />
              <b>{!isPaid ? `${FREE_CREDITS} credits` : yearly ? `${(p.monthly_credits * 12).toLocaleString()} credits/year` : `${p.monthly_credits.toLocaleString()} credits/month`}</b>
              <span>1 credit processes 1 minute of source video</span></p>
            <ul className="plan-list">
              <li className="hi"><Icon name="check" size={16} />{isPaid ? `${p.monthly_credits.toLocaleString()} credits every month` : `${FREE_CREDITS} credits when you sign up`}</li>
              {isPaid && yearly && <li><Icon name="check" size={16} />All {(p.monthly_credits * 12).toLocaleString()} credits up front</li>}
              <li><Icon name="check" size={16} />{p.max_side >= 1080 ? "1080p" : "720p"} exports</li>
              <li><Icon name="check" size={16} />Reframe and caption {perJob(p.max_render_min)} per job</li>
              <li><Icon name="check" size={16} />Videos and clips kept 7 days</li>
            </ul>
            <p className="plan-plus">{isPaid ? "Everything in Free, plus:" : "Every plan includes:"}</p>
            <ul className="plan-list">
              {(isPaid ? ["Unused credits roll over", "Priority support"] : INCLUDED).map((f) => <li key={f}><Icon name="check" size={16} />{f}</li>)}
            </ul>
          </article>
        );
      })}
    </div>
  );
}
