"use client";
import { useEffect, useState } from "react";
import { api } from "./api";

// GET /v1/billing/plans, asked once per visit (public). The free plan carries `signup_credits`: what a new account
// gets once its email is confirmed. Nothing about a plan is hardcoded in the site.
type PlansReply = { currency: string; plans: { id: string; price_month_cents: number; signup_credits?: number }[] };
let asked: Promise<PlansReply | null> | null = null;
export function loadPlans(): Promise<PlansReply | null> {
  if (!asked) asked = api<PlansReply>("/v1/billing/plans", { auth: false }).catch(() => { asked = null; return null; });
  return asked;
}

// The sign-up grant, or null while asking or when this API does not say (then the copy leaves the number out).
export function useSignupCredits(): number | null {
  const [n, setN] = useState<number | null>(null);
  useEffect(() => {
    let on = true;
    loadPlans().then((r) => {
      const free = r?.plans.find((p) => p.price_month_cents === 0 && typeof p.signup_credits === "number");
      if (on && free) setN(free.signup_credits!);
    });
    return () => { on = false; };
  }, []);
  return n;
}

// "100 free credits" or "Free credits" when the number is not known.
export const freeCredits = (n: number | null) => (n === null ? "Free credits" : `${n.toLocaleString()} free credits`);
