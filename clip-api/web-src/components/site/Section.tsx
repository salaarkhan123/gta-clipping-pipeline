// A landing-page section: eyebrow, heading and lead centred over the content, on the 1200 px grid.
// Spacing and type come from the tokens (text-eyebrow, text-h2, text-lead, max-w-site, max-w-prose).
import { ComingSoonBadge } from "../ComingSoonBadge";

// `bright`: white instead of the usual 50% white (the hero's eyebrow).
export function Eyebrow({ icon, bright, children, className = "" }: { icon?: React.ReactNode; bright?: boolean; children: React.ReactNode; className?: string }) {
  return (
    <p className={`inline-flex items-center gap-2 text-eyebrow uppercase ${bright ? "text-fg" : "text-fg-2"} ${className}`}>
      {icon && <span className="grid place-items-center [&_svg]:h-[1.1em] [&_svg]:w-[1.1em]" aria-hidden="true">{icon}</span>}{children}
    </p>
  );
}

export function Section({ id, eyebrow, icon, title, sub, soon, children, className = "" }: {
  id?: string; eyebrow?: string; icon?: React.ReactNode; title: React.ReactNode; sub?: React.ReactNode; soon?: boolean; children?: React.ReactNode; className?: string;
}) {
  return (
    <section id={id} className={`px-gutter py-[clamp(64px,8vw,120px)] ${className}`}>
      <div className="mx-auto max-w-site">
        <header className="mx-auto mb-[clamp(32px,4vw,56px)] grid max-w-prose justify-items-center gap-3 text-center">
          {(eyebrow || soon) && <div className="flex flex-wrap items-center justify-center gap-2">
            {eyebrow && <Eyebrow icon={icon}>{eyebrow}</Eyebrow>}{soon && <ComingSoonBadge />}</div>}
          <h2 className="text-h2 text-fg">{title}</h2>
          {sub && <p className="text-lead text-fg-2">{sub}</p>}
        </header>
        {children}
      </div>
    </section>
  );
}
