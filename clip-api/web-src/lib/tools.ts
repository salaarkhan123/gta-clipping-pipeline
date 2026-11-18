import type { IconName } from "@/components/dash/Icon";

// Every tool the app names, in one list: the Home grid and the top bar's Tools menu both read it.
// `tool` opens that tool on a video the user picks (the project page's ?tool=); `page` opens that page on a video
// the user picks (?id=); `href` is a page of its own. A tool with none of them is planned but not built: it is
// shown as "Coming soon" and is never a link. `needs` names a switch in GET /v1/languages that must be on
// (summaries are off until the owner picks a provider). `badge: "new"` is only for tools that work today.
export type ToolEntry = { id: string; icon: IconName; name: string; text: string; tool?: "clips" | "find" | "captions" | "reframe";
  page?: string; href?: string; needs?: "summaries"; badge?: "new" };

export const TOOLS: ToolEntry[] = [
  { id: "clips", icon: "scissors", name: "AI Clipping", text: "Finds the best moments in a stream and cuts them into ranked clips.", tool: "clips" },
  { id: "find", icon: "search", name: "Find Moments", text: "Type what was said or shown and get a clip of every match.", tool: "find", badge: "new" },
  { id: "templates", icon: "gamepad", name: "Game Templates", text: "Layouts, captions and length tuned to a game, in one pick.", href: "/dashboard/templates/", badge: "new" },
  { id: "captions", icon: "captions", name: "AI Captions", text: "Burn word-by-word captions into any part of a video.", tool: "captions" },
  { id: "reframe", icon: "reframe", name: "AI Reframe", text: "Reshape wide footage to vertical, portrait or square.", tool: "reframe" },
  { id: "editor", icon: "sliders", name: "Video Editor", text: "Trim, cut by transcript and restyle a clip: open Edit on any clip.", href: "/dashboard/library/?view=clips", badge: "new" },
  { id: "highlights", icon: "bolt", name: "One-Click Highlights", text: "One montage from the best parts of a stream." },
  { id: "transcripts", icon: "transcript", name: "Video Transcripts", text: "Everything that was said, with timestamps, as TXT, SRT or VTT.", page: "/dashboard/transcript/", badge: "new" },
  { id: "summary", icon: "summary", name: "Video Summary", text: "A title, summary, tags and timed highlights of a stream.", page: "/dashboard/summary/", needs: "summaries", badge: "new" },
  { id: "thumbnail", icon: "image", name: "AI Thumbnail", text: "Cover images made for each clip." },
  { id: "enhancer", icon: "sparkle", name: "Video Enhancer", text: "Sharper, higher-resolution footage." },
  { id: "live", icon: "live", name: "Live Clipping", text: "Clips cut while the stream is still live." },
];

// `on`: the switches from GET /v1/languages (null while asking: a tool that needs one waits as "Coming soon").
export const isBuilt = (t: ToolEntry, on: Record<string, boolean> | null = null) => !!(t.tool || t.page || t.href) && (!t.needs || !!on?.[t.needs]);
// Where a working tool goes from anywhere in the app: a page, or Home with the tool to open on a video.
export const toolHref = (t: ToolEntry) => t.href || `/dashboard/?tool=${t.id}`;
