"use client";
// Template tiles with real footage from the media pipeline (public/media/templates/, one item per template id, each
// cut from that template's own game). A template with no item stays an empty tile: never another game's footage.
import { useRef } from "react";
import { Footage, useItems } from "./Footage";
import { useInView } from "./motion";

// Template ids and names as the API serves them (GET /v1/templates).
// Prefer GTA / shooter / racing over the Fortnite template as the primary example row.
const SHOWN: [string, string][] = [["gta-rp-reaction", "GTA RP reaction"], ["valorant-clutch", "Spike clutch"],
  ["racing-gameplay", "Racing"], ["shooter-gameplay", "Warzone"]];

export function TemplatePreviews() {
  const items = useItems("templates"), box = useRef<HTMLDivElement>(null), seen = useInView(box);
  return (
    <div ref={box} className="grid grid-cols-4 gap-1.5">
      {SHOWN.map(([id, name]) => {
        const item = items.find((i) => i.id === id) ?? null;
        return (
          <div key={id} className="grid min-w-0 gap-1">
            <span className="relative block aspect-[9/16] overflow-hidden rounded-[8px] bg-black/40 ring-1 ring-white/10">
              {item && <Footage section="templates" item={item} play={seen} />}
            </span>
            <span className="truncate text-[10px] text-white/60">{name}</span>
          </div>
        );
      })}
    </div>
  );
}
