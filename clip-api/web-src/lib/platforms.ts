// Link-import platforms the site may name, each added only after its imports are checked in production (owner
// rule). Empty today: no platform is verified yet, so the copy names none. Add one name at a time, e.g. "YouTube",
// "Twitch" (VODs and clips) or "Kick", and every link prompt on the site picks it up.
export const VERIFIED_PLATFORMS: readonly string[] = [];

// "Twitch", "Twitch or Kick", "YouTube, Twitch or Kick".
export const platformNames = (list: readonly string[] = VERIFIED_PLATFORMS) =>
  list.length < 2 ? list.join("") : `${list.slice(0, -1).join(", ")} or ${list[list.length - 1]}`;

// "a recorded video link", or "a recorded Twitch or Kick video link" once those are verified.
export const linkPhrase = (list: readonly string[] = VERIFIED_PLATFORMS) =>
  list.length ? `a recorded ${platformNames(list)} video link` : "a recorded video link";

// The link field's placeholder and the paste bars: "Paste a recorded video link or upload a file."
export const pastePrompt = (list: readonly string[] = VERIFIED_PLATFORMS) => `Paste ${linkPhrase(list)} or upload a file.`;
