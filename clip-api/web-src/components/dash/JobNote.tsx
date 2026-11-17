const STAGES: Record<string, string> = {
  starting: "Starting", downloading: "Getting your video", probing: "Reading the video", chat_motion: "Watching chat",
  audio: "Listening for reactions", transcribing: "Transcribing speech", indexing_frames: "Looking through the frames",
  searching: "Searching", rendering: "Rendering clips", writing_titles: "Writing titles", uploading: "Saving clips", done: "Done",
};
export const isActive = (j: any) => j.status === "QUEUED" || j.status === "RUNNING";

// One job as a line: what it is, how far along, a way to stop it, and why it failed. `children` is its result.
export function JobNote({ job, name, onCancel, children }: { job: any; name: string; onCancel: (jobId: string) => void; children?: React.ReactNode }) {
  return (
    <article className={`job ${job.status.toLowerCase()}`}>
      <div className="job-head">
        <strong>{name}</strong>
        <span className="status">{isActive(job) ? `${STAGES[job.stage] || "Queued"} ${job.progress}%`
          : job.status === "FAILED" ? "Failed, credits refunded" : job.status === "CANCELLED" || job.status === "CANCELED" ? "Cancelled" : "Done"}</span>
      </div>
      {isActive(job) && <><progress max={100} value={job.progress} aria-label={`${name} progress`} />
        <button className="link" onClick={() => onCancel(job.job_id)}>Cancel</button></>}
      {job.status === "FAILED" && job.error && <p className="error">{job.error.message}</p>}
      {children && <div className="job-body">{children}</div>}
    </article>
  );
}
