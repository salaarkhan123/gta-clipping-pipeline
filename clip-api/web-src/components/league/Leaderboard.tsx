// The leaderboard: the top three as cards, everyone else as rows. Real entries only; with none it says so.
import { EmptyState } from "@/components/ui/EmptyState";
import { moment, ordinal, Row, views } from "@/lib/league";
import { ClipThumb, CreatorAvatar, CreatorName, WatchLink } from "./Bits";

const PLACE_RING = ["shadow-[inset_0_0_0_1px_rgba(184,255,60,.55)]", "shadow-[inset_0_0_0_1px_rgba(255,255,255,.22)]", "shadow-[inset_0_0_0_1px_rgba(255,182,72,.35)]"];
const PLACE_INK = ["text-lime", "text-fg", "text-warn"];

const Status = ({ row }: { row: Row }) => (
  <span className={`inline-flex h-6 items-center rounded-[6px] px-2 text-[12px] font-medium ${row.status === "winner" ? "bg-lime/[.14] text-lime" : "bg-control text-fg-2"}`}>
    {row.status === "winner" ? `${ordinal(row.final_place || row.rank)} place, confirmed` : "Provisional"}</span>
);

function Podium({ row }: { row: Row }) {
  const i = row.rank - 1;
  return (
    <li className={`grid grid-cols-[88px_1fr] gap-4 rounded-card bg-card p-4 ${PLACE_RING[i]} narrow:grid-cols-[72px_1fr] narrow:gap-3`}>
      <ClipThumb row={row} className="aspect-[9/16] w-full" />
      <div className="grid min-w-0 content-between gap-3">
        <div className="grid gap-2">
          <span className={`font-sans text-[34px] font-semibold leading-none tracking-[-0.03em] tabular-nums ${PLACE_INK[i]}`}>#{row.rank}</span>
          <span className="flex min-w-0 items-center gap-2"><CreatorAvatar name={row.username} color={row.avatar} size={28} />
            <CreatorName row={row} className="min-w-0 truncate text-[16px] font-semibold" /></span>
          <span className="truncate text-[13px] text-fg-2">{row.game || "Game not set"}</span>
        </div>
        <div className="grid gap-1.5">
          <span className="font-sans text-[20px] font-semibold leading-none tabular-nums text-fg">{views(row.views)}{row.views !== null && <span className="ml-1.5 text-[12px] font-normal text-fg-2">views</span>}</span>
          <span className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px]"><Status row={row} /><WatchLink row={row} /></span>
        </div>
      </div>
    </li>
  );
}

export function Leaderboard({ rows, updatedAt, empty }: { rows: Row[]; updatedAt: string | null; empty: React.ReactNode }) {
  if (!rows.length) return <EmptyState icon="chart" title="No entries on the board yet">{empty}</EmptyState>;
  const top = rows.filter((r) => r.rank <= 3), rest = rows.filter((r) => r.rank > 3);
  return (
    <div className="grid min-w-0 gap-4 [&>*]:min-w-0">
      <ol className="m-0 grid list-none grid-cols-3 gap-4 p-0 mid:grid-cols-1" aria-label="Top three">
        {top.map((r) => <Podium key={r.rank} row={r} />)}
      </ol>
      {rest.length > 0 && (
        <div className="relative overflow-x-auto rounded-card bg-card shadow-card">
          <table className="w-full min-w-[640px] border-collapse narrow:min-w-[560px] text-left text-[14px]">
            <caption className="sr-only">Leaderboard from fourth place</caption>
            <thead><tr className="text-[12px] uppercase tracking-[.06em] text-fg-3">
              {["Rank", "Creator", "Game", "Video", "Views", "Status"].map((h) => <th key={h} scope="col" className="px-4 py-3 font-medium">{h}</th>)}</tr></thead>
            <tbody>{rest.map((r) => (
              <tr key={r.rank} className="border-0 border-t border-solid border-line-soft">
                <td className="px-4 py-3 font-semibold tabular-nums text-fg-2">#{r.rank}</td>
                <td className="px-4 py-3"><span className="flex items-center gap-2.5"><CreatorAvatar name={r.username} color={r.avatar} size={28} /><CreatorName row={r} className="font-medium" /></span></td>
                <td className="px-4 py-3 text-fg-2">{r.game || "Not set"}</td>
                <td className="px-4 py-3"><span className="flex items-center gap-3"><ClipThumb row={r} className="h-12 w-[27px] flex-none !rounded-[6px] [&>span[role=img]]:hidden" /><WatchLink row={r} /></span></td>
                <td className="px-4 py-3 font-semibold tabular-nums text-fg">{views(r.views)}</td>
                <td className="px-4 py-3"><Status row={r} /></td>
              </tr>))}</tbody>
          </table>
        </div>
      )}
      <p className="m-0 text-[13px] leading-[1.5] text-fg-2">
        Views are read by hand from each video&apos;s public page and are unverified. {updatedAt ? `Last updated ${moment(updatedAt)}.` : "No count has been recorded yet."} Rankings are provisional until winners are confirmed.
      </p>
    </div>
  );
}
