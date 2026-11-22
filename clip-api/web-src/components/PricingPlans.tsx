"use client";
// Plan cards, shared by the public pricing page and the in-app one. Prices, credits, limits and any listed
// features come from the server's plan config (GET /v1/billing/plans); nothing about a plan is set here.
import { money } from "@/lib/api";
import { freeCredits } from "@/lib/plans";
import { Icon } from "./dash/Icon";

// `description` and `features` are optional fields of a plan in the config; when they are missing the card
// shows only what the numbers say.
export type Plan = { id: string; name: string; price_month_cents: number; price_year_cents: number; monthly_credits: number;
  max_side: number; max_render_min: number | null; description?: string; features?: string[]; signup_credits?: number };

// What every plan can use: the product's tools, the same on every plan.
export const INCLUDED = ["AI clip finder with an AI rating on every clip", "Find any moment by speech or what's on screen", "Automatic facecam detection",
  "9:16, 4:5, 1:1 and 16:9", "Caption styles, SRT and VTT export", "AI titles and hashtags", "API access and the agent skill"];
// An export cap from the plan config (`max_side`, pixels on the short side) in the words people use.
export const exportName = (px: number) => (px >= 2160 ? "4K" : px >= 1440 ? "2K" : px >= 1080 ? "1080p" : px >= 720 ? "720p" : `${px}p`);
const perJob = (min: number | null) => (min ? `up to ${min >= 60 ? `${min / 60} hr` : `${min} min`}` : "any length");

// The real yearly saving, worked out from the plans the server returns. 0 when there is none.
export function yearlySaving(plans: Plan[]): number {
  const paid = plans.filter((p) => p.price_month_cents > 0);
  return paid.length ? Math.round(100 * (1 - Math.min(...paid.map((p) => p.price_year_cents / (p.price_month_cents * 12))))) : 0;
}

export function PeriodToggle({ yearly, onChange, save }: { yearly: boolean; onChange: (yearly: boolean) => void; save: number }) {
  const button = (on: boolean) => `inline-flex h-8 cursor-pointer items-center rounded-control border-0 px-4 font-sans text-[13px] font-medium leading-[normal] transition-colors duration-base ${on ? "bg-btn text-btn-ink" : "bg-transparent text-fg-2 hover:text-text"}`;
  return (
    <div className="inline-flex items-center gap-[2px] rounded-control bg-control p-[3px]" role="group" aria-label="Billing period">
      <button type="button" className={button(!yearly)} aria-pressed={!yearly} onClick={() => onChange(false)}>Monthly</button>
      <button type="button" className={button(yearly)} aria-pressed={yearly} onClick={() => onChange(true)}>Yearly
        {save > 0 && <span className={`ml-[6px] rounded-[6px] px-[6px] py-px text-[11px] ${yearly ? "bg-black/10 text-btn-ink" : "bg-lime/[.14] text-lime"}`}>Save {save}%</span>}</button>
    </div>
  );
}

const Check = ({ hi }: { hi?: boolean }) => <Icon name="check" size={16} className={`mt-[2px] ${hi ? "text-lime" : "text-muted"}`} />;

// `onPick(plan)` starts checkout for a paid plan; the free plan links to `freeHref`.
export function PlanCards({ plans, currency, yearly, current, busy, onPick, freeHref }: { plans: Plan[]; currency: string; yearly: boolean;
  current: string | null; busy: string; onPick: (p: Plan) => void; freeHref: string }) {
  const paid = plans.filter((p) => p.price_month_cents > 0);
  const popular = paid.length >= 2 ? paid[1].id : paid[0]?.id;
  const fmt = (c: number) => money(c, currency).replace(/\.00$/, "");
  return (
    <div className="grid grid-cols-[repeat(auto-fit,minmax(240px,1fr))] items-stretch gap-4 text-left">
      {plans.map((p) => {
        const isPaid = p.price_month_cents > 0, pop = p.id === popular;
        const perMonth = yearly ? p.price_year_cents / 12 : p.price_month_cents;
        const button = `btn w-full ${pop ? "primary" : "ghost"}`;
        return (
          <article key={p.id} aria-label={`${p.name} plan`} className={`relative flex flex-col gap-[14px] rounded-card border border-solid bg-card p-6 shadow-card ${pop ? "border-lime" : "border-transparent"}`}>
            <h3 className="flex items-center justify-between gap-2 font-sans text-[20px] font-semibold leading-[normal]">{p.name}
              {pop && <span className="rounded-[6px] bg-lime/[.14] px-[7px] py-[3px] text-[11px] font-medium leading-none text-lime">Most popular</span>}</h3>
            {p.description && <p className="min-h-[42px] text-[14px] text-muted">{p.description}</p>}
            <div className="flex flex-wrap items-baseline gap-2">
              {isPaid && yearly && perMonth < p.price_month_cents && <s className="text-[18px] font-medium text-fg-3" aria-label={`was ${fmt(p.price_month_cents)}`}>{fmt(p.price_month_cents)}</s>}
              <b className="font-sans text-[36px] font-semibold leading-none tracking-[-0.02em] text-text">{fmt(Math.round(perMonth))}</b><small className="text-[14px] font-normal text-fg-2">/ month</small>
            </div>
            <p className="-mt-2 min-h-[20px] text-[13px] text-muted">{!isPaid ? "Free forever" : yearly ? `Billed ${fmt(p.price_year_cents)} yearly` : "Billed monthly"}</p>
            {current === p.id ? <button className="btn ghost w-full" disabled>Your plan</button>
              : isPaid ? <button className={button} disabled={busy === p.id} onClick={() => onPick(p)}>{busy === p.id ? "Opening checkout…" : `Get ${p.name}`}</button>
              : <a className={button} href={freeHref}>Start free</a>}
            <p className="grid grid-cols-[auto_1fr] gap-x-[10px] gap-y-[2px] border-0 border-b border-solid border-line pb-[14px]">
              <Icon name="bolt" size={18} className="row-span-2 mt-[2px] text-lime" />
              <b className="text-[15px] font-medium">{!isPaid ? freeCredits(p.signup_credits ?? null) : `${p.monthly_credits.toLocaleString()} credits every month${yearly ? ", billed yearly" : ""}`}</b>
              <span className="text-[13px] text-muted">1 credit processes 1 minute of source video</span></p>
            <ul className="grid list-none gap-[10px] text-[14px]">
              {!isPaid && <li className="flex items-start gap-[10px] text-lime"><Check hi />{freeCredits(p.signup_credits ?? null)} when you confirm your email</li>}
              <li className="flex items-start gap-[10px] text-label"><Check />{exportName(p.max_side)} exports</li>
              <li className="flex items-start gap-[10px] text-label"><Check />Reframe and caption {perJob(p.max_render_min)} per job</li>
              {(p.features || []).map((f) => <li key={f} className="flex items-start gap-[10px] text-label"><Check />{f}</li>)}
            </ul>
            {!isPaid && <>
              <p className="border-0 border-t border-solid border-line pt-[14px] font-sans text-[13px] font-normal uppercase leading-[normal] text-fg-2">Every plan includes:</p>
              <ul className="grid list-none gap-[10px] text-[14px]">{INCLUDED.map((f) => <li key={f} className="flex items-start gap-[10px] text-label"><Check />{f}</li>)}</ul>
            </>}
          </article>
        );
      })}
    </div>
  );
}
