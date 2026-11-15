// Thin client for the public ClutchClips API. The website uses the same endpoints customers do.
export const API = (process.env.NEXT_PUBLIC_API_URL || "https://api.clutchclips.io").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) { super(message); }
}

const KEY = "cc_token";
export const getToken = () => (typeof window === "undefined" ? null : window.localStorage.getItem(KEY));
export const setToken = (t: string | null) => (t ? localStorage.setItem(KEY, t) : localStorage.removeItem(KEY));

export async function api<T = any>(path: string, opts: { method?: string; body?: unknown; auth?: boolean } = {}): Promise<T> {
  const headers: Record<string, string> = {};
  const token = getToken();
  if (token && opts.auth !== false) headers.Authorization = `Bearer ${token}`;
  if (opts.body !== undefined) headers["Content-Type"] = "application/json";
  let res: Response;
  try {
    res = await fetch(API + path, { method: opts.method || (opts.body !== undefined ? "POST" : "GET"), headers,
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined });
  } catch {
    throw new ApiError(0, "network", "Can't reach ClutchClips right now. Check your connection and try again.");
  }
  const text = await res.text();
  let data: any = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = text; }
  if (!res.ok) {
    if (res.status === 401 && token) setToken(null);
    throw new ApiError(res.status, data?.error?.code || "error", data?.error?.message || `Request failed (${res.status}).`);
  }
  return data as T;
}

// Upload with progress. The file is sent as the raw request body.
export function uploadFile(file: File, onProgress: (fraction: number) => void): { promise: Promise<any>; abort: () => void } {
  const xhr = new XMLHttpRequest();
  const promise = new Promise<any>((resolve, reject) => {
    xhr.open("POST", `${API}/v1/uploads?filename=${encodeURIComponent(file.name)}`);
    xhr.setRequestHeader("Authorization", `Bearer ${getToken()}`);
    xhr.setRequestHeader("Content-Type", "application/octet-stream");
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(e.loaded / e.total);
    xhr.onerror = () => reject(new ApiError(0, "network", "The upload was interrupted. Check your connection and try again."));
    xhr.onabort = () => reject(new ApiError(0, "aborted", "Upload cancelled."));
    xhr.onload = () => {
      let data: any = null;
      try { data = JSON.parse(xhr.responseText); } catch {}
      if (xhr.status >= 200 && xhr.status < 300) resolve(data);
      else reject(new ApiError(xhr.status, data?.error?.code || "error", data?.error?.message || `Upload failed (${xhr.status}).`));
    };
    xhr.send(file);
  });
  return { promise, abort: () => xhr.abort() };
}

// A file picked on the home page before signing in, handed to the dashboard after sign-up.
let pending: File | null = null;
export const setPendingFile = (f: File | null) => { pending = f; };
export const takePendingFile = () => { const f = pending; pending = null; return f; };

export const VIDEO_TYPES = ".mp4,.mov,.mkv,.webm,.m4v,.avi,.flv,.ts";
export const money = (cents: number, currency = "usd") =>
  new Intl.NumberFormat("en-US", { style: "currency", currency: currency.toUpperCase(), maximumFractionDigits: cents % 100 ? 2 : 0 }).format(cents / 100);
export const clock = (s: number) => {
  const t = Math.max(0, Math.round(s));
  const h = Math.floor(t / 3600), m = Math.floor((t % 3600) / 60), sec = t % 60;
  return h ? `${h}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}` : `${m}:${String(sec).padStart(2, "0")}`;
};
export const FREE_CREDITS = 100; // keep in sync with FREE_SIGNUP_CREDITS on the server
