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
export const Soon = () => <small className="soon-tag">Coming soon</small>;
