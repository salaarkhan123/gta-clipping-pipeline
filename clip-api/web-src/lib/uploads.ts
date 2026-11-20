// Upload soft-delete helpers. DELETE /v1/uploads/{upload_id} (PR #239) marks deleted_at and hides the row;
// no ledger change. The control calls `api` itself so this module stays free of the fetch client for node tests.

export type DeletedUpload = { deleted: boolean; upload_id: string };

export function uploadDeletePath(uploadId: string) {
  return `/v1/uploads/${encodeURIComponent(uploadId)}`;
}
