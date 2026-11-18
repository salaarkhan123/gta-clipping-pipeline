"use client";
import { useEffect, useState } from "react";
import { api } from "./api";

// Which routes this API has, and which fields their bodies take, read from its own OpenAPI document. Used for
// routes that are still being built (quotes, re-export, saving an edit): a control for one appears only once the
// API serves it. Nothing is sent to a route to find out, so no probe can ever start a paid job.
type Spec = { paths?: Record<string, Record<string, any>>; components?: { schemas?: Record<string, any> } };
let asked: Promise<Spec> | null = null;
function spec(): Promise<Spec> {
  if (!asked) {
    asked = api<Spec>("/openapi.json", { auth: false });
    asked.catch(() => { asked = null; });
  }
  return asked.catch(() => ({}));
}

const bodyOf = (s: Spec, method: string, path: string) =>
  resolve(s, s.paths?.[path]?.[method]?.requestBody?.content?.["application/json"]?.schema);
function resolve(s: Spec, schema: any): any {
  if (!schema) return null;
  if (schema.$ref) return s.components?.schemas?.[String(schema.$ref).split("/").pop()!] || null;
  const some = schema.anyOf?.find((x: any) => x.$ref || x.properties);
  return some ? resolve(s, some) : schema;
}

// What one route takes: its body's field names, and the fields of each nested object (`options`, `edit`).
export type Route = { fields: string[]; nested: Record<string, string[]> };
// The route, or null when this API does not serve it (the same as a 404 or 405).
export async function route(method: "post" | "patch", path: string): Promise<Route | null> {
  const s = await spec();
  if (!s.paths?.[path]?.[method]) return null;
  const props: Record<string, any> = bodyOf(s, method, path)?.properties || {};
  const nested = Object.fromEntries(Object.entries(props).map(([k, v]) => [k, Object.keys(resolve(s, v)?.properties || {})]));
  return { fields: Object.keys(props), nested };
}

// The routes the editor, the job form and the results grid look for.
export const QUOTE = "/v1/clips/quote", EXPORT = "/v1/clips/export", EXPORT_QUOTE = "/v1/clips/export/quote", CLIP = "/v1/clips/{clip_id}";
export type Routes = { quote: Route | null; exportRoute: Route | null; exportQuote: Route | null; patchClip: Route | null };
let all: Promise<Routes> | null = null;
export function routes(): Promise<Routes> {
  if (!all) all = Promise.all([route("post", QUOTE), route("post", EXPORT), route("post", EXPORT_QUOTE), route("patch", CLIP)])
    .then(([quote, exportRoute, exportQuote, patchClip]) => ({ quote, exportRoute, exportQuote, patchClip }));
  return all;
}

// null while asking.
export function useRoutes(): Routes | null {
  const [r, setR] = useState<Routes | null>(null);
  useEffect(() => { let on = true; routes().then((x) => on && setR(x)); return () => { on = false; }; }, []);
  return r;
}
