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
- takedown.py   remove everything that came from a source URL or an account's imports
"""

UPLOAD_INSTEAD = "Upload the file instead."


class Refused(Exception):
    """An import that cannot go ahead. `message` is safe to show to the user and says what to do next."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message
