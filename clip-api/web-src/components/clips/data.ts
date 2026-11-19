"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { loadPlans } from "@/lib/plans";

// The game each template belongs to, by template id: GET /v1/templates?kind=game and GET /v1/templates/games (both
// public). A run's game is the game of the template it was started with (job options `template`); a run without
// one has no game, and the card shows none.
let games: Promise<Map<string, string>> | null = null;
function loadGames(): Promise<Map<string, string>> {
  if (!games) {
    games = Promise.all([api("/v1/templates?kind=game", { auth: false }), api("/v1/templates/games", { auth: false })])
      .then(([t, g]) => {
        const names = new Map<string, string>((g?.games || []).map((x: any) => [x.id, x.name]));
        return new Map<string, string>((t?.templates || []).filter((x: any) => x.game)
          .map((x: any) => [x.id, names.get(x.game) || x.game]));
      });
    games.catch(() => { games = null; });
  }
  return games.catch(() => new Map());
}
export function useGameOfTemplate(): Map<string, string> {
  const [m, setM] = useState<Map<string, string>>(new Map());
  useEffect(() => { let on = true; loadGames().then((x) => on && setM(x)); return () => { on = false; }; }, []);
  return m;
}

// The account's export resolution cap, the short side in pixels (`max_side` of its plan in GET /v1/billing/plans).
// null while asking, or when the plan is not listed there (a legacy plan): the server still applies the cap.
export function usePlanCap(planId: string | undefined): number | null {
  const [cap, setCap] = useState<number | null>(null);
  useEffect(() => {
    let on = true;
    loadPlans().then((r) => {
      const plan: any = r?.plans.find((p) => p.id === (planId || "free"));
      if (on) setCap(typeof plan?.max_side === "number" ? plan.max_side : null);
    });
    return () => { on = false; };
  }, [planId]);
  return cap;
}
