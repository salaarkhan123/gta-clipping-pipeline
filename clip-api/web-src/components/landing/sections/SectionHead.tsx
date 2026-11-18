// The heading every landing section starts with: a small label, the title, one line under it.
export type Eyebrow = "spark" | "loop" | "edit" | "people";

const PATHS: Record<Eyebrow, React.ReactNode> = {
  spark: <path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8zM19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z" />,
  loop: <><path d="M4 12a8 8 0 0 1 14-5.3L20 9" /><path d="M20 4v5h-5" /><path d="M20 12a8 8 0 0 1-14 5.3L4 15" /><path d="M4 20v-5h5" /></>,
  edit: <><path d="M4 20h4L19 9l-4-4L4 16z" /><path d="M14 6l4 4" /></>,
  people: <><circle cx="9" cy="8" r="3.5" /><path d="M2.5 20a6.5 6.5 0 0 1 13 0" /><path d="M16 4.6a3.5 3.5 0 0 1 0 6.8M18 14a6.5 6.5 0 0 1 3.5 6" /></>,
};

export function SectionHead({ id, icon, label, title, sub }: { id: string; icon: Eyebrow; label: string; title: React.ReactNode; sub: React.ReactNode }) {
  return (
    <header className="mx-auto mb-12 flex max-w-[900px] flex-col items-center px-5 text-center narrow:mb-8">
      <p className="mb-3 flex items-center gap-2 text-[15px] font-semibold uppercase tracking-[.08em] text-white/60">
        <svg viewBox="0 0 24 24" className="h-[18px] w-[18px]" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{PATHS[icon]}</svg>
        {label}
      </p>
      <h2 id={id} className="text-[clamp(32px,4.4vw,56px)] font-semibold leading-[1.08] tracking-[-.02em]">{title}</h2>
      <p className="mt-4 max-w-[720px] text-[clamp(16px,1.5vw,20px)] text-white/60">{sub}</p>
    </header>
  );
}
