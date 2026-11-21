"""Platform registry. A destination appears only when its client id and secret are set."""
from dataclasses import dataclass, field
from typing import Callable

from ..config import Settings, get_settings

# Operational readiness for honest UI labels. Never "live" until production verified.
READINESS = {
    "youtube": "awaiting_approval",      # code ready; needs Google OAuth verification + authorized test
    "tiktok": "awaiting_approval",
    "instagram": "awaiting_approval",
    "facebook": "awaiting_approval",
    "x": "held",                         # paid API; owner OK required
    "linkedin": "held",
}


@dataclass(frozen=True)
class PlatformSpec:
    id: str
    name: str
    readiness: str                       # awaiting_approval | not_configured | held | production_verified
    min_sec: float
    max_sec: float
    max_bytes: int
    title_max: int | None
    caption_max: int
    privacy_options: tuple[str, ...]
    fields: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()
    offered: bool = True                 # False = never in UI (X, LinkedIn held)


def _creds(s: Settings, platform: str) -> tuple[str, str]:
    return (
        getattr(s, f"{platform}_client_id", "") or "",
        getattr(s, f"{platform}_client_secret", "") or "",
    )


def configured(platform: str, s: Settings | None = None) -> bool:
    cid, secret = _creds(s or get_settings(), platform)
    return bool(cid and secret)


def specs(s: Settings | None = None) -> list[dict]:
    """Public platform list for GET /v1/publish/platforms. Tokens never included."""
    s = s or get_settings()
    out = []
    for spec in _CATALOG:
        if not spec.offered:
            continue
        ready = spec.readiness
        if not configured(spec.id, s):
            ready = "not_configured"
        out.append({
            "id": spec.id,
            "name": spec.name,
            "readiness": ready,
            "operational": ready == "production_verified",
            "configured": configured(spec.id, s),
            "limits": {
                "min_sec": spec.min_sec,
                "max_sec": spec.max_sec,
                "max_bytes": spec.max_bytes,
                "title_max": spec.title_max,
                "caption_max": spec.caption_max,
            },
            "privacy_options": list(spec.privacy_options),
            "fields": list(spec.fields),
            "notes": list(spec.notes),
        })
    return out


_CATALOG: tuple[PlatformSpec, ...] = (
    PlatformSpec(
        id="youtube", name="YouTube Shorts", readiness=READINESS["youtube"],
        min_sec=1, max_sec=180, max_bytes=256 * 1024 ** 3,
        title_max=100, caption_max=5000,
        privacy_options=("public", "unlisted", "private"),
        fields=("made_for_kids", "contains_synthetic_media", "paid_product_placement"),
        notes=("Needs a full-quality export before publish.",
               "Not live until an authorized YouTube test succeeds."),
    ),
    PlatformSpec(
        id="tiktok", name="TikTok", readiness=READINESS["tiktok"],
        min_sec=3, max_sec=600, max_bytes=4 * 1024 ** 3,
        title_max=None, caption_max=2200,
        privacy_options=(),  # from creator_info at confirm time; no default
        fields=("disable_comment", "disable_duet", "disable_stitch", "commercial_disclosure"),
        notes=("Posts stay private to the creator until TikTok audits ClutchClips.",
               "Confirm panel must show nickname, privacy with no default, and Music Usage line."),
    ),
    PlatformSpec(
        id="instagram", name="Instagram Reels", readiness=READINESS["instagram"],
        min_sec=3, max_sec=900, max_bytes=300 * 1024 ** 2,
        title_max=None, caption_max=2200,
        privacy_options=("public",),
        fields=(),
        notes=("Professional Instagram accounts only.",
               "Meta App Review and Business Verification required before public use."),
    ),
    PlatformSpec(
        id="facebook", name="Facebook Reels", readiness=READINESS["facebook"],
        min_sec=3, max_sec=90, max_bytes=1 * 1024 ** 3,
        title_max=255, caption_max=2200,
        privacy_options=("public",),
        fields=(),
        notes=("Facebook Pages only (not personal profiles).",
               "Clips longer than 90 seconds cannot be Reels."),
    ),
    PlatformSpec(
        id="x", name="X", readiness=READINESS["x"],
        min_sec=0.5, max_sec=1200, max_bytes=8 * 1024 ** 3,
        title_max=None, caption_max=280,
        privacy_options=("public",),
        offered=False,
        notes=("Held: X API is paid per post. Owner pricing OK required."),
    ),
)


def spec_of(platform: str) -> PlatformSpec | None:
    return next((p for p in _CATALOG if p.id == platform), None)


def validate_text(platform: str, title: str | None, caption: str, hashtags: list[str]) -> list[str]:
    """Return human reasons the text is unfit; empty means OK. Never silently truncate."""
    p = spec_of(platform)
    if not p:
        return [f"Unknown platform {platform}."]
    reasons = []
    if p.title_max is not None and title is not None and len(title) > p.title_max:
        reasons.append(f"Title is {len(title)} characters; {p.name} allows {p.title_max}.")
    body = caption or ""
    if hashtags:
        tag = " ".join(h if h.startswith("#") else f"#{h}" for h in hashtags)
        body = f"{body}\n{tag}".strip() if body else tag
    if len(body) > p.caption_max:
        reasons.append(f"Caption is {len(body)} characters; {p.name} allows {p.caption_max}.")
    return reasons


DurationCheck = Callable[[float, int | None], list[str]]


def validate_media(platform: str, duration_sec: float, size_bytes: int | None) -> list[str]:
    p = spec_of(platform)
    if not p:
        return [f"Unknown platform {platform}."]
    reasons = []
    if duration_sec < p.min_sec:
        reasons.append(f"{p.name} needs at least {p.min_sec:g} s; this clip is {duration_sec:.1f} s.")
    if duration_sec > p.max_sec:
        reasons.append(f"{p.name} allows up to {p.max_sec:g} s; this clip is {duration_sec:.1f} s.")
    if size_bytes is not None and size_bytes > p.max_bytes:
        mb = size_bytes / (1024 ** 2)
        cap = p.max_bytes / (1024 ** 2)
        reasons.append(f"{p.name} allows up to {cap:g} MB; this export is {mb:.1f} MB.")
    return reasons
