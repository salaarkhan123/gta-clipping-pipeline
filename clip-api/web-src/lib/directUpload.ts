// Resumable upload straight to the bucket (POST /v1/uploads/multipart, API docs "Direct uploads"): the API signs
// one PUT per part, the browser sends four parts at a time, and a part that fails is retried. After a dropped
// connection, picking the same file again resumes: the upload token is kept per file (name, size, modified time)
// and the API lists the parts it already holds. The API records the upload only when every part is stored.
// No imports, so node --test runs it with fake requests (tests/direct-upload.test.mjs).

export type Part = { part_number: number; size: number; url: string };
type Batch = { part_size: number; part_count: number; done: number[]; parts: Part[] };
export type Deps = {
  call: (path: string, body: unknown) => Promise<any>;     // POST to the API; rejects with an error that has .code
  put: (url: string, body: Blob, onProgress: (loaded: number) => void) => { promise: Promise<void>; abort: () => void };
  error: (code: string, message: string) => Error;
  saved?: Pick<Storage, "getItem" | "setItem" | "removeItem">;    // localStorage
  wait?: (ms: number) => Promise<void>;
};
type FileLike = Blob & { name: string; lastModified: number };

export const CONCURRENCY = 4;
export const TRIES = 3;

export function directUpload(file: FileLike, onProgress: (fraction: number) => void, deps: Deps) {
  const key = `cc_upload:${file.name}:${file.size}:${file.lastModified}`;
  const keep = {
    get: () => { try { return deps.saved?.getItem(key) ?? null; } catch { return null; } },
    set: (v: string) => { try { deps.saved?.setItem(key, v); } catch { /* private window: no resume after reload */ } },
    drop: () => { try { deps.saved?.removeItem(key); } catch { /* as above */ } },
  };
  const wait = deps.wait || ((ms: number) => new Promise<void>((r) => setTimeout(r, ms)));
  const sending = new Map<number, { abort: () => void; loaded: number }>();
  let token: string | null = null, stopped = false, halted = false, stored = 0;
  const report = () => {
    let n = stored;
    sending.forEach((s) => { n += s.loaded; });
    onProgress(Math.min(1, n / file.size));
  };
  const check = () => { if (stopped) throw deps.error("aborted", "Upload cancelled."); };
  const partBytes = (b: Batch, n: number) => (n === b.part_count ? file.size - b.part_size * (b.part_count - 1) : b.part_size);

  const next = (): Promise<Batch> => deps.call("/v1/uploads/multipart/parts", { upload_token: token });
  async function begin(): Promise<Batch> {
    token = keep.get();
    if (token) {
      try { return await next(); }
      catch (e: any) {
        if (e?.code !== "not_found" && e?.code !== "upload_gone") throw e;   // expired or finished: start over
        keep.drop();
      }
    }
    const up = await deps.call("/v1/uploads/multipart", { filename: file.name, size_bytes: file.size });
    token = up.upload_token;
    keep.set(up.upload_token);
    return next();
  }

  async function send(p: Part, partSize: number) {
    const start = (p.part_number - 1) * partSize;
    const body = file.slice(start, start + p.size);
    for (let tries = 1; ; tries++) {
      check();
      const slot = { abort: () => {}, loaded: 0 };
      const req = deps.put(p.url, body, (loaded) => { slot.loaded = loaded; report(); });
      slot.abort = req.abort;
      sending.set(p.part_number, slot);
      try {
        await req.promise;
        sending.delete(p.part_number);
        stored += p.size;
        report();
        return;
      } catch {
        sending.delete(p.part_number);
        check();
        if (tries >= TRIES || halted) {
          halted = true;
          throw deps.error("network", "The upload was interrupted. Check your connection and pick the same file again to resume.");
        }
        await wait(1000 * 3 ** (tries - 1));
      }
    }
  }

  const promise = (async () => {
    let batch = await begin();
    stored = batch.done.reduce((n, d) => n + partBytes(batch, d), 0);
    report();
    while (batch.parts.length) {
      check();
      const queue = [...batch.parts], size = batch.part_size;
      await Promise.all(Array.from({ length: Math.min(CONCURRENCY, queue.length) }, async () => {
        for (let p = queue.shift(); p && !halted; p = queue.shift()) await send(p, size);
      }));
      batch = await next();
    }
    check();
    const upload = await deps.call("/v1/uploads/multipart/complete", { upload_token: token });
    keep.drop();
    return upload;
  })().catch((e) => {
    if (stopped && token) {                               // cancelled: the bucket drops the parts
      deps.call("/v1/uploads/multipart/abort", { upload_token: token }).catch(() => {});
      keep.drop();
    }
    throw e;
  });

  const abort = () => {
    stopped = true;
    sending.forEach((s) => s.abort());
  };
  return { promise, abort };
}
