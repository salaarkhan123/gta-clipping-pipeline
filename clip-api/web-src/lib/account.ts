"use client";
import { useEffect, useState } from "react";
import { loadPlans } from "./plans";

// An account's plan id as people read it. The name comes from GET /v1/billing/plans; a plan that is no longer on
// sale (a legacy id) is tidied from its id: "pro_v2" reads "Pro", "agency" reads "Agency".
export const tidyPlan = (id: string) => {
  const base = (id || "free").replace(/_v\d+$/, "").replace(/[_-]+/g, " ");
  return base.charAt(0).toUpperCase() + base.slice(1);
};

export function usePlanName(id: string): string {
  const [name, setName] = useState(() => tidyPlan(id));
  useEffect(() => {
    let on = true;
    setName(tidyPlan(id));
    loadPlans().then((r) => {
      const found = (r?.plans as { id: string; name?: string }[] | undefined)?.find((p) => p.id === id);
      if (on && found?.name) setName(found.name);
    });
    return () => { on = false; };
  }, [id]);
  return name;
}

// What the shell shows as the account's name: the part of the email before the @.
export const accountName = (email: string) => (email || "").split("@")[0] || email;
