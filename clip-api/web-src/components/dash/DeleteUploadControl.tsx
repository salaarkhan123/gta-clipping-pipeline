"use client";
// Soft-delete one upload this account owns (DELETE /v1/uploads/{id}, PR #239). Explicit confirm before the call;
// ApiError (including 404 when the route is not on this API yet) is shown — never treated as success.
import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import { DeletedUpload, uploadDeletePath } from "@/lib/uploads";
import { Icon } from "./Icon";

export function DeleteUploadControl({ uploadId, name, onDeleted, compact }: {
  uploadId: string; name?: string; onDeleted: (uploadId: string) => void; compact?: boolean;
}) {
  const [ask, setAsk] = useState(false), [busy, setBusy] = useState(false), [problem, setProblem] = useState("");

  async function confirm() {
    setProblem(""); setBusy(true);
    try {
      const r = await api<DeletedUpload>(uploadDeletePath(uploadId), { method: "DELETE" });
      if (!r?.deleted) throw new ApiError(0, "error", "The upload was not deleted.");
      onDeleted(r.upload_id || uploadId);
      setAsk(false);
    } catch (e) {
      setProblem(e instanceof Error ? e.message : "The upload could not be deleted.");
    } finally { setBusy(false); }
  }

  if (ask) {
    return (
      <div role="group" aria-label={`Delete ${name || "this video"}?`}
        className={`grid gap-1 rounded-8 border border-solid border-line bg-card-2 p-2 ${compact ? "text-[12px]" : "text-[13px]"}`}
        onClick={(e) => e.preventDefault()}>
        <span className="text-label">Remove this video from your library? Clips stay until they expire.</span>
        <div className="flex flex-wrap items-center gap-2">
          <button type="button" className="btn small ghost danger" disabled={busy} onClick={confirm}>
            {busy ? "Deleting…" : "Delete"}</button>
          <button type="button" className="btn small ghost" disabled={busy} onClick={() => { setAsk(false); setProblem(""); }}>
            Keep</button>
        </div>
        {problem && <p className="error m-0" role="alert">{problem}</p>}
      </div>
    );
  }

  return (
    <div className="grid gap-1" onClick={(e) => e.preventDefault()}>
      <button type="button" className={compact ? "icon-btn h-8 w-8 border-0" : "btn small ghost danger gap-1"}
        aria-label={`Delete ${name || "video"}`} title="Delete" onClick={() => setAsk(true)}>
        <Icon name="trash" size={compact ? 16 : 15} />{!compact && "Delete"}
      </button>
      {problem && <p className="error m-0" role="alert">{problem}</p>}
    </div>
  );
}
