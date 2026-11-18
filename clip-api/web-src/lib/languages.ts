"use client";
import { useEffect, useState } from "react";
import { api } from "./api";

// GET /v1/languages: every language code with its name and whether speech in it can be transcribed here, plus
// whether translation and summaries are switched on. Public. Asked once per visit; a failed request is retried.
export type Languages = { languages: { code: string; name: string; transcribe: boolean }[]; translation: boolean; summaries: boolean; speakers: boolean };
let asked: Promise<Languages | null> | null = null;
export function loadLanguages(): Promise<Languages | null> {
  if (!asked) asked = api<Languages>("/v1/languages", { auth: false }).catch(() => { asked = null; return null; });
  return asked;
}

// null while asking (or when the list cannot be had).
export function useLanguages(): Languages | null {
  const [l, setL] = useState<Languages | null>(null);
  useEffect(() => { let on = true; loadLanguages().then((x) => on && setL(x)); return () => { on = false; }; }, []);
  return l;
}

// The on/off switches only, for tools that need one (Video Summary needs `summaries`).
export function useLanguageSwitches(): Record<string, boolean> | null {
  const l = useLanguages();
  return l ? { translation: l.translation, summaries: l.summaries } : null;
}
