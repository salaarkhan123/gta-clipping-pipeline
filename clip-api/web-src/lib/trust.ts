// Copyright and likeness cases: the words the screens use for the API's values, and how a 422 names its field.
// The API (app/routes_trust.py, app/trust_decisions.py) enforces every rule; the screens only explain them.

export const KIND_LABEL: Record<string, string> = { copyright: "Copyright notice", likeness: "Likeness report" };

export const STATUS_LABEL: Record<string, string> = {
  received: "Received", in_review: "In review", info_requested: "Waiting for the claimant", disabled: "Content disabled",
  removed: "Content removed", rejected: "Rejected", withdrawn: "Withdrawn", restored: "Content restored",
  counter_noticed: "Counter-notice sent", closed: "Closed",
};
export const STATUSES = Object.keys(STATUS_LABEL);

// What happened to one reported item (case_targets.state).
export const TARGET_LABEL: Record<string, string> = {
  live: "Live", disabled: "Hidden", gone: "Already gone", restored: "Restored", expired: "Expired, not restored",
  deleted: "Files deleted",
};

// A 422 names its field first ("work: String should have…", "reported_urls.2: …"); a rule over the whole report
// names it as its first word ("address is required for a copyright notice"). `field` is null when it names none.
export function fieldError(message: string, fields: readonly string[]): { field: string | null; text: string } {
  const m = /^([a-z_]+)(?:\.(\d+))?: ([\s\S]*)$/.exec(message);
  if (m && fields.includes(m[1])) return { field: m[1], text: m[2] !== undefined ? `Line ${Number(m[2]) + 1}: ${m[3]}` : m[3] };
  const first = /^([a-z_]+)\b/.exec(message)?.[1];
  if (first && fields.includes(first)) return { field: first, text: message };
  return { field: null, text: message };
}

export const when = (iso: string | null | undefined) => (iso ? new Date(iso).toLocaleString(undefined, {
  year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "");

// Moves focus to the element with this id once React has drawn it.
export const focusSoon = (id: string) => requestAnimationFrame(() => document.getElementById(id)?.focus());
