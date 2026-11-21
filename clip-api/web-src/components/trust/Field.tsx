// Form pieces shared by the report, counter-notice and decision forms: a field's error, and the attributes that tie
// an input to its hint and its error.

export const INPUT = "w-full";
export const ERR = "text-[13px] font-medium text-danger";
export const HINT = "text-[13px] text-muted";
export const LINK = "text-lime underline";

// id, aria-invalid and aria-describedby for the input `id`, whose hint is `${id}-hint` and error `${id}-err`.
export function wire(id: string, error?: string, hint?: boolean) {
  const by = [hint ? `${id}-hint` : "", error ? `${id}-err` : ""].filter(Boolean).join(" ");
  return { id, "aria-invalid": error ? (true as const) : undefined, "aria-describedby": by || undefined };
}

export function Err({ id, text }: { id: string; text?: string }) {
  return text ? <span id={`${id}-err`} className={ERR}>{text}</span> : null;
}
