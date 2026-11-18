import { ComingSoonBadge } from "@/components/ComingSoonBadge";

// The dashboard's own line icons: 24 px grid, drawn for ClutchClips. Decorative, so always hidden from screen readers.
const PATHS = {
  home: <><path d="M4 11.5 12 4l8 7.5" /><path d="M6.5 10v9.5h11V10" /><path d="M10 19.5v-5h4v5" /></>,
  library: <><rect x="3" y="7.5" width="14" height="12" rx="2" /><path d="M7 4.5h12a2 2 0 0 1 2 2V15" /></>,
  calendar: <><rect x="4" y="5.5" width="16" height="14" rx="2.5" /><path d="M4 10h16M8.5 3.5v4M15.5 3.5v4" /></>,
  brand: <><path d="M12 3.5c3 3.6 5.5 6.3 5.5 9.5a5.5 5.5 0 0 1-11 0c0-3.2 2.5-5.9 5.5-9.5Z" /><path d="M9.5 13.5a2.5 2.5 0 0 0 2.5 2.5" /></>,
  tag: <><path d="M3.5 12.5V5A1.5 1.5 0 0 1 5 3.5h7.5l8 8-9 9-8-8Z" /><circle cx="8" cy="8" r="1.3" /></>,
  code: <path d="m8 8-4.5 4L8 16M16 8l4.5 4L16 16M13.5 5l-3 14" />,
  card: <><rect x="3" y="5.5" width="18" height="13" rx="2.5" /><path d="M3 10h18M7 15h3" /></>,
  upload: <><path d="M12 15.5v-11M7.5 9 12 4.5 16.5 9" /><path d="M4.5 15v3A1.5 1.5 0 0 0 6 19.5h12a1.5 1.5 0 0 0 1.5-1.5v-3" /></>,
  link: <><path d="M10 14a4 4 0 0 0 5.7 0l3-3A4 4 0 0 0 13 5.3l-1 1" /><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1" /></>,
  stack: <><path d="m12 3.5 8.5 4.5-8.5 4.5L3.5 8 12 3.5Z" /><path d="m3.5 12 8.5 4.5 8.5-4.5M3.5 16l8.5 4.5 8.5-4.5" /></>,
  scissors: <><circle cx="6.5" cy="7" r="2.5" /><circle cx="6.5" cy="17" r="2.5" /><path d="M8.7 8.3 20 17M8.7 15.7 20 7" /></>,
  search: <><circle cx="11" cy="11" r="6.5" /><path d="m16 16 4.5 4.5" /></>,
  gamepad: <><path d="M7.5 7.5h9a5 5 0 0 1 4.9 4l.6 4a2.6 2.6 0 0 1-4.6 2L15.5 15h-7l-1.9 2.5a2.6 2.6 0 0 1-4.6-2l.6-4a5 5 0 0 1 4.9-4Z" /><path d="M8 10v3M6.5 11.5h3M15.5 10.5h.01M17.5 12.5h.01" /></>,
  captions: <><rect x="3" y="5" width="18" height="14" rx="2.5" /><path d="M7 14.5h4M13.5 14.5H17M7 11h2M11.5 11H17" /></>,
  reframe: <><rect x="8" y="3.5" width="8" height="17" rx="2" /><path d="M3.5 8.5v7M20.5 8.5v7" /></>,
  sliders: <><path d="M4 7h9M17 7h3M4 12h3M11 12h9M4 17h11M19 17h1" /><circle cx="15" cy="7" r="2" /><circle cx="9" cy="12" r="2" /><circle cx="17" cy="17" r="2" /></>,
  bolt: <path d="M13 3 5 13.5h6L10 21l8-10.5h-6L13 3Z" />,
  transcript: <><path d="M6.5 3.5H14l4 4V19a1.5 1.5 0 0 1-1.5 1.5h-10A1.5 1.5 0 0 1 5 19V5a1.5 1.5 0 0 1 1.5-1.5Z" /><path d="M14 3.5V8h4M8.5 12h7M8.5 16h5" /></>,
  summary: <path d="M8.5 7h11M8.5 12h11M8.5 17h7M4.5 7h.01M4.5 12h.01M4.5 17h.01" />,
  image: <><rect x="3.5" y="5" width="17" height="14" rx="2.5" /><circle cx="9" cy="10" r="1.6" /><path d="m5 17.5 4.5-4 3 2.5 3.5-4 3.5 4" /></>,
  sparkle: <><path d="M11 4.5 12.7 9.3 17.5 11l-4.8 1.7L11 17.5l-1.7-4.8L4.5 11l4.8-1.7L11 4.5Z" /><path d="M18.5 15.5v4M16.5 17.5h4" /></>,
  live: <><circle cx="12" cy="12" r="2.5" /><path d="M7.4 7.4a6.5 6.5 0 0 0 0 9.2M16.6 7.4a6.5 6.5 0 0 1 0 9.2M4.6 4.6a10.5 10.5 0 0 0 0 14.8M19.4 4.6a10.5 10.5 0 0 1 0 14.8" /></>,
  external: <><path d="M14 4.5h5.5V10M19.5 4.5 11 13" /><path d="M17.5 14v4a1.5 1.5 0 0 1-1.5 1.5H6A1.5 1.5 0 0 1 4.5 18V8A1.5 1.5 0 0 1 6 6.5h4" /></>,
  menu: <path d="M4 7h16M4 12h16M4 17h16" />,
  close: <path d="m6 6 12 12M18 6 6 18" />,
  film: <><rect x="3.5" y="5" width="17" height="14" rx="2.5" /><path d="m10 9.5 4.5 2.5-4.5 2.5v-5Z" /></>,
  logout: <path d="M10 4.5H6A1.5 1.5 0 0 0 4.5 6v12A1.5 1.5 0 0 0 6 19.5h4M15 8l4 4-4 4M19 12H9.5" />,
  check: <path d="m5 12.5 4.5 4.5L19 7.5" />,
  plus: <path d="M12 5v14M5 12h14" />,
  pencil: <><path d="m14.5 5.5 4 4L8 20H4v-4L14.5 5.5Z" /><path d="m12.5 7.5 4 4" /></>,
  trash: <><path d="M4.5 7h15M9.5 7V4.5h5V7M6.5 7l1 12.5h9l1-12.5" /><path d="M10 11v5M14 11v5" /></>,
  download: <><path d="M12 4.5v11M7.5 11l4.5 4.5 4.5-4.5" /><path d="M4.5 15v3A1.5 1.5 0 0 0 6 19.5h12a1.5 1.5 0 0 0 1.5-1.5v-3" /></>,
  like: <><path d="M7.5 10.5 11 4a2.2 2.2 0 0 1 2.6 2.6l-.8 3.4h5a2 2 0 0 1 2 2.4l-1.1 5.5a2 2 0 0 1-2 1.6H7.5v-9Z" /><path d="M7.5 10.5h-3v9h3" /></>,
  dislike: <><path d="M16.5 13.5 13 20a2.2 2.2 0 0 1-2.6-2.6l.8-3.4h-5a2 2 0 0 1-2-2.4l1.1-5.5a2 2 0 0 1 2-1.6H16.5v9Z" /><path d="M16.5 13.5h3v-9h-3" /></>,
  bookmark: <path d="M7 4.5h10a1 1 0 0 1 1 1V20l-6-4-6 4V5.5a1 1 0 0 1 1-1Z" />,
  send: <path d="M20 4 10.5 13.5M20 4l-6 16-3.5-6.5L4 10l16-6Z" />,
  arrow: <path d="M5 12h14M13 6l6 6-6 6" />,
  back: <path d="M19 12H5M11 6l-6 6 6 6" />,
  globe: <><circle cx="12" cy="12" r="8.5" /><path d="M3.5 12h17M12 3.5c2.4 2.6 3.5 5.4 3.5 8.5s-1.1 5.9-3.5 8.5c-2.4-2.6-3.5-5.4-3.5-8.5s1.1-5.9 3.5-8.5Z" /></>,
  chevron: <path d="m7 10 5 5 5-5" />,
  grid: <><rect x="4" y="4" width="6.5" height="6.5" rx="1.5" /><rect x="13.5" y="4" width="6.5" height="6.5" rx="1.5" /><rect x="4" y="13.5" width="6.5" height="6.5" rx="1.5" /><rect x="13.5" y="13.5" width="6.5" height="6.5" rx="1.5" /></>,
  play: <path d="M7.5 5v14l11-7-11-7Z" />,
  pause: <path d="M8 5v14M16 5v14" />,
  music: <><path d="M9 17.5V6l10-2v11.5" /><circle cx="6.5" cy="17.5" r="2.5" /><circle cx="16.5" cy="15.5" r="2.5" /></>,
  transitions: <><path d="M4 6.5h6l4 11h6" /><path d="M4 17.5h6l1.5-4M14 6.5h6" /></>,
  mic: <><rect x="9" y="3.5" width="6" height="11" rx="3" /><path d="M5.5 11.5a6.5 6.5 0 0 0 13 0M12 18v2.5" /></>,
  text: <path d="M5 6.5V5h14v1.5M12 5v14M9 19h6" />,
  hook: <><path d="M5 5.5h14v9H11l-4 3.5v-3.5H5v-9Z" /><path d="M9 9.5h6M9 12h3.5" /></>,
  skipBack: <><path d="M6 5v14" /><path d="M18.5 5.5v13L9 12l9.5-6.5Z" /></>,
  skipForward: <><path d="M18 5v14" /><path d="M5.5 5.5v13L15 12 5.5 5.5Z" /></>,
  zoomIn: <><circle cx="11" cy="11" r="6.5" /><path d="m16 16 4.5 4.5M8.5 11h5M11 8.5v5" /></>,
  zoomOut: <><circle cx="11" cy="11" r="6.5" /><path d="m16 16 4.5 4.5M8.5 11h5" /></>,
  smile: <><circle cx="12" cy="12" r="8.5" /><path d="M8.5 14a4 4 0 0 0 7 0M9 9.5h.01M15 9.5h.01" /></>,
  shapes: <><circle cx="8" cy="8" r="4" /><path d="M14 13.5h6.5V20H14z" /><path d="m15.5 4 3.5 6h-7l3.5-6Z" /></>,
  volume: <><path d="M4.5 9.5h3l4.5-4v13l-4.5-4h-3v-5Z" /><path d="M15.5 9a4 4 0 0 1 0 6M18 6.5a7.5 7.5 0 0 1 0 11" /></>,
  wave: <path d="M4 12h1.5M7.5 8v8M11 5v14M14.5 9v6M18 7v10M20.5 12H20" />,
  expand: <path d="M14 4.5h5.5V10M19.5 4.5 13.5 10.5M10 19.5H4.5V14M4.5 19.5l6-6" />,
  palette: <><path d="M12 3.5a8.5 8.5 0 1 0 0 17c1.4 0 2-1 2-2 0-1.5-1.5-1.8-1.5-3s1-2 2.5-2H18a2.5 2.5 0 0 0 2.5-2.5c0-4.3-3.8-7.5-8.5-7.5Z" /><path d="M7.5 12h.01M9.5 8h.01M14.5 8h.01" /></>,
  eye: <><path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12Z" /><circle cx="12" cy="12" r="3" /></>,
  translate: <><path d="M4 6h9M8.5 4v2c0 4-2 7-4.5 8.5M6.5 10c1 2 3 3.5 5.5 4" /><path d="m13 20 3.5-8 3.5 8M14.2 17.5h4.6" /></>,
  rewind: <><path d="M11 6.5 4.5 12l6.5 5.5v-11Z" /><path d="M19.5 6.5 13 12l6.5 5.5v-11Z" /></>,
  info: <><circle cx="12" cy="12" r="8.5" /><path d="M12 11v5M12 8h.01" /></>,
  phone: <rect x="7.5" y="3.5" width="9" height="17" rx="2" />,
  cloud: <path d="M7 18.5h10.5a4 4 0 0 0 .6-7.95A5.5 5.5 0 0 0 7.4 9.1 4.75 4.75 0 0 0 7 18.5Z" />,
  wand: <><path d="m4.5 19.5 10-10M13 6.5l2.5 2.5" /><path d="M17.5 3.5v3M16 5h3M19.5 10.5v2M18.5 11.5h2M9.5 3.5v2M8.5 4.5h2" /></>,
  folder: <path d="M3.5 7A1.5 1.5 0 0 1 5 5.5h4.5l2 2.5H19A1.5 1.5 0 0 1 20.5 9.5V17A1.5 1.5 0 0 1 19 18.5H5A1.5 1.5 0 0 1 3.5 17V7Z" />,
  undo: <><path d="M9 7.5 5 11.5l4 4" /><path d="M5 11.5h9.5a4.5 4.5 0 0 1 0 9H12" /></>,
  // Dashboard shell (agent E).
  redo: <><path d="M15 7.5l4 4-4 4" /><path d="M19 11.5H9.5a4.5 4.5 0 0 0 0 9H12" /></>,
  bell: <><path d="M6.5 16.5V11a5.5 5.5 0 0 1 11 0v5.5l1.5 2H5l1.5-2Z" /><path d="M10 20.5a2.2 2.2 0 0 0 4 0" /></>,
  chart: <><path d="M4.5 19.5h15" /><path d="M7.5 16v-4M12 16V7.5M16.5 16v-6" /></>,
  share: <><circle cx="17" cy="6" r="2.5" /><circle cx="7" cy="12" r="2.5" /><circle cx="17" cy="18" r="2.5" /><path d="m9.2 10.8 5.6-3.5M9.2 13.2l5.6 3.5" /></>,
  flask: <><path d="M9.5 3.5h5M10.5 3.5v5.5L5 18.3a1.5 1.5 0 0 0 1.3 2.2h11.4a1.5 1.5 0 0 0 1.3-2.2L13.5 9V3.5" /><path d="M7.5 14.5h9" /></>,
  book: <><path d="M4.5 5.5A1.5 1.5 0 0 1 6 4h5.5v15.5H6a1.5 1.5 0 0 0-1.5 1.5V5.5Z" /><path d="M19.5 5.5A1.5 1.5 0 0 0 18 4h-5.5v15.5H18a1.5 1.5 0 0 1 1.5 1.5V5.5Z" /></>,
  template: <><rect x="4" y="4" width="16" height="16" rx="2.5" /><path d="M4 9.5h16M9.5 9.5V20" /></>,
  sidebar: <><rect x="3.5" y="4.5" width="17" height="15" rx="2.5" /><path d="M9.5 4.5v15" /></>,
  key: <><circle cx="8" cy="15" r="3.5" /><path d="m10.5 12.5 8-8M15.5 7.5l2.5 2.5M17.5 5.5l2 2" /></>,
  font: <path d="M4.5 19 9.5 5h1l5 14M6.5 14h7M15.5 19l2.5-6.5L20.5 19M16.3 17h3.4" />,
  shield: <path d="M12 3.5 19 6v5.5c0 4.3-3 7.6-7 9-4-1.4-7-4.7-7-9V6l7-2.5Z" />,
  swap: <path d="M7 4.5 4 7.5l3 3M4 7.5h12M17 13.5l3 3-3 3M20 16.5H8" />,
} as const;

export type IconName = keyof typeof PATHS;

// `className` adds utility classes (a colour, say) next to `ico`.
export function Icon({ name, size = 20, className }: { name: IconName; size?: number; className?: string }) {
  return (
    <svg className={className ? `ico ${className}` : "ico"} width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">{PATHS[name]}</svg>
  );
}

// Marks something that is planned but not built. Never put this on a working link.
export const Soon = ({ short }: { short?: boolean }) => <ComingSoonBadge short={short} className="ml-1" />;
