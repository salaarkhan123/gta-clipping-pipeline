"""Link import: a public video link becomes an upload.

The rule for everything in this package (CLAUDE.md, "Ingestion"): public, non-DRM content only. No logins,
cookies, accounts, proxies, IP rotation, client spoofing or impersonation, geo-bypass, or any other way around a
block, paywall, age gate or rate limit. A site that refuses is a clean failure that tells the user to upload the
file. Every import needs the user's confirmation that they may clip the content, is logged before anything is
fetched, and can be removed again with the takedown flow.

- sources.py    which hosts are allowed and which downloader handles a link
- fetch.py      direct, Google Drive and Dropbox links: one https download, every hop checked and pinned
- platforms.py  Twitch, Kick and YouTube through yt-dlp, with a fixed set of options
- preview.py    what a link is (title, channel, length, thumbnail) before an import: metadata only
- runner.py     the worker's side: download, check, store, turn the placeholder into a usable upload
- copies.py     what an account already has from a link, so the same video is never downloaded twice
- takedown.py   remove everything that came from a source URL or an account's imports
"""
from dataclasses import dataclass

UPLOAD_INSTEAD = "Upload the file instead."
SPAN_SLACK = 1.0            # an end this far past the video's length is read as "to the end"


class Refused(Exception):
    """An import that cannot go ahead. `message` is safe to show to the user and says what to do next.
    `about`: what the link is, when its address alone says so (a channel page), for the link preview."""

    def __init__(self, code: str, message: str, about: dict | None = None):
        super().__init__(message)
        self.code, self.message, self.about = code, message, about


@dataclass(frozen=True)
class Span:
    """The part of a source video an import takes, in seconds of that video. `end` None: to the end."""
    start: float = 0.0
    end: float | None = None

    @property
    def whole(self) -> bool:
        return self.start <= 0 and self.end is None

    def as_list(self) -> list[float | None]:
        return [round(self.start, 3), None if self.end is None else round(self.end, 3)]

    @classmethod
    def of(cls, value) -> "Span":
        """From what a job stores (`[start, end]`; anything else is the whole video)."""
        if not isinstance(value, (list, tuple)) or len(value) != 2:
            return cls()
        return cls(float(value[0] or 0.0), None if value[1] is None else float(value[1]))

    def holds(self, other: "Span") -> bool:
        """Whether every second of `other` is inside this span."""
        if other.start < self.start - 0.5:
            return False
        return self.end is None or (other.end is not None and other.end <= self.end + 0.5)


def make_span(start_sec: float | None, end_sec: float | None) -> Span:
    """A request's start_sec / end_sec as a Span. Refused (a 422) when they are not a range."""
    start = float(start_sec or 0.0)
    if start < 0 or (end_sec is not None and float(end_sec) <= start):
        raise Refused("bad_range", "start_sec must be 0 or more and end_sec must be after start_sec.")
    return Span(start, None if end_sec is None else float(end_sec))


def fit_span(span: Span, duration: float | None, min_sec: float, max_sec: float, open_end: bool = False) -> Span:
    """`span` laid on a video `duration` seconds long (None: not known before the download). The end is clamped to
    the video, and the part taken must be `min_sec` to `max_sec` long. `open_end`: the video is still being
    recorded, so "to the end" is pinned to what exists now. Raises Refused."""
    start, end = span.start, span.end
    if duration is not None:
        if start >= duration or (end is not None and end > duration + SPAN_SLACK):
            raise Refused("bad_range", f"The range must lie inside the video (0 to {duration:.0f} seconds).")
        if open_end:
            end = duration if end is None else min(end, duration)
        elif end is not None and end >= duration:
            end = None                      # to the end of a finished video
    last = end if end is not None else duration
    if last is not None:
        if last - start < min_sec:
            raise Refused("video_too_short", f"Minimum video length is {min_sec:g} seconds.")
        if last - start > max_sec:
            raise Refused("video_too_long", f"Maximum video length is {int(max_sec // 3600)} hours. Choose a "
                                            "shorter range of the video.")
    return Span(start, end)
