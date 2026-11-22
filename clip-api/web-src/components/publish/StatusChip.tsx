import { PostStatus, STATUS_LABEL, STATUS_TONE } from "@/lib/publish";

export function StatusChip({ status, compact }: { status: PostStatus; compact?: boolean }) {
  return (
    <span
      className={`inline-flex items-center rounded-pill border border-solid font-medium ${STATUS_TONE[status]} ${
        compact ? "px-2 py-[1px] text-[11px]" : "px-2.5 py-[2px] text-[12px]"
      }`}
    >
      {STATUS_LABEL[status]}
    </span>
  );
}
