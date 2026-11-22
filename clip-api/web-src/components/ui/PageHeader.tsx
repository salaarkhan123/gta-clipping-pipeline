// The row at the top of an app page: the title, one grey hint beside it, the page's actions on the right.
export function PageHeader({ title, hint, children, className = "" }: {
  title: React.ReactNode; hint?: React.ReactNode; children?: React.ReactNode; className?: string;
}) {
  return (
    <header className={`flex min-h-[40px] flex-wrap items-center justify-between gap-x-6 gap-y-3 ${className}`}>
      <div className="flex min-w-0 flex-wrap items-baseline gap-x-5 gap-y-1">
        <h1 className="m-0 font-sans text-[24px] font-semibold leading-[1.2] tracking-[-0.01em] text-fg narrow:text-[22px]">{title}</h1>
        {hint && <p className="m-0 text-[14px] text-fg-2">{hint}</p>}
      </div>
      {children && <div className="flex flex-wrap items-center gap-3">{children}</div>}
    </header>
  );
}
