// Undo and redo over a value being edited. `past` and `future` hold earlier and undone values; the newest is last
// in `past`, the next to redo is first in `future`. Plain data, no imports, so it is tested on its own.
export type History<T> = { past: T[]; now: T; future: T[] };
export const HISTORY_MAX = 50;
export const startHistory = <T>(now: T): History<T> => ({ past: [], now, future: [] });
export const change = <T extends object>(h: History<T>, patch: Partial<T>): History<T> =>
  ({ past: [...h.past, h.now].slice(-HISTORY_MAX), now: { ...h.now, ...patch }, future: [] });
export const undo = <T>(h: History<T>): History<T> => !h.past.length ? h
  : { past: h.past.slice(0, -1), now: h.past[h.past.length - 1], future: [h.now, ...h.future] };
export const redo = <T>(h: History<T>): History<T> => !h.future.length ? h
  : { past: [...h.past, h.now], now: h.future[0], future: h.future.slice(1) };
