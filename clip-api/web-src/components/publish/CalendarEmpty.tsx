import Link from "next/link";
import { PLATFORM_LABEL, SAMPLE_SCHEDULE, SCHEDULE_TIPS } from "@/lib/publish";
import { StatusChip } from "./StatusChip";

type Props = {
  mode: "disabled" | "empty";
  reason?: string;
  onSchedule?: () => void;
  canSchedule?: boolean;
};

/** Honest empty / disabled states plus a clearly labeled sample week for gaming creators. */
export function CalendarEmpty({ mode, reason, onSchedule, canSchedule }: Props) {
  return (
    <div className="grid gap-5">
      <div className="grid gap-3 rounded-20 border border-solid border-line-soft bg-card p-5">
        <h2 className="m-0 text-[18px] font-semibold tracking-[-0.02em]">
          {mode === "disabled" ? "Publishing is not enabled yet" : "No posts on this calendar yet"}
        </h2>
        <p className="m-0 max-w-[62ch] text-[14px] text-muted">
          {mode === "disabled"
            ? (reason || "Publishing is not enabled on this server yet.")
              + " Calendar stays honest: no fake scheduled or published rows until the owner turns publishing on."
            : "Schedule an exported clip to YouTube Shorts, TikTok, or Reels. Status here comes from the job queue — never a fake success toast."}
        </p>
        <div className="flex flex-wrap gap-2">
          {mode === "empty" && canSchedule && onSchedule && (
            <button type="button" className="btn small primary" onClick={onSchedule}>Schedule a clip</button>
          )}
          <Link href="/dashboard/social-accounts/" className="btn small ghost">Social accounts</Link>
          <Link href="/dashboard/library/?view=clips" className="btn small ghost">Open clips</Link>
        </div>
        <ul className="m-0 grid list-disc gap-1.5 pl-5 text-[13px] text-fg-3">
          {SCHEDULE_TIPS.map((t) => <li key={t}>{t}</li>)}
        </ul>
      </div>

      <section className="grid gap-3" aria-labelledby="sample-schedule-title">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h3 id="sample-schedule-title" className="m-0 text-[16px] font-semibold">
            Sample week for a gaming creator
          </h3>
          <span className="rounded-pill border border-solid border-line-soft bg-chip px-2.5 py-[2px] text-[11px] font-medium text-muted">
            Example only
          </span>
        </div>
        <p className="m-0 max-w-[60ch] text-[13px] text-muted">
          Illustrative slots so you can see how scheduled, published, and failed posts will look. These are not real posts and never hit a platform.
        </p>
        <ul className="m-0 grid list-none gap-2 p-0 mid:grid-cols-2">
          {SAMPLE_SCHEDULE.map((s) => (
            <li
              key={s.id}
              className="grid gap-2 rounded-16 border border-dashed border-line-strong bg-panel p-4 opacity-90"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-[14px] font-medium text-soft">
                  {PLATFORM_LABEL[s.platform] || s.platform}
                </span>
                <StatusChip status={s.status} compact />
              </div>
              <p className="m-0 text-[14px] text-text">{s.title}</p>
              <div className="flex flex-wrap items-baseline justify-between gap-2 text-[12.5px] text-muted">
                <span className="tabular-nums">{s.whenLabel}</span>
                <span>{s.tip}</span>
              </div>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
