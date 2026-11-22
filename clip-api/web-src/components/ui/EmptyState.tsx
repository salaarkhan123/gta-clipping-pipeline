import { Icon, IconName } from "@/components/dash/Icon";

// What a region shows when it has nothing yet: what belongs here, and the one action that fills it.
export function EmptyState({ icon = "film", title, children, action, className = "" }: {
  icon?: IconName; title: string; children?: React.ReactNode; action?: React.ReactNode; className?: string;
}) {
  return (
    <div className={`grid place-items-center gap-3 rounded-card border border-dashed border-line-strong px-6 py-14 text-center ${className}`}>
      <span className="grid h-11 w-11 place-items-center rounded-12 bg-control text-fg-2" aria-hidden="true"><Icon name={icon} size={20} /></span>
      <h2 className="m-0 text-[16px] font-semibold tracking-[-0.01em] text-text">{title}</h2>
      {children && <p className="m-0 max-w-[420px] text-[14px] leading-[1.45] text-fg-2">{children}</p>}
      {action}
    </div>
  );
}
