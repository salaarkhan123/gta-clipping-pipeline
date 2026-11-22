"""The Creators League rules shown on the website and accepted with every entry.

DRAFT. This text was not written or reviewed by a lawyer and makes no claim that the competition meets any
contest, sweepstakes, consumer or tax law. Every section marked `needs_legal_review` holds a placeholder the
owner's lawyer must replace before a competition with cash prizes is opened (LEAGUE_CASH_PRIZES_APPROVED).
Change VERSION whenever the text changes: each entry records the version its creator accepted.
"""
VERSION = "draft-2026-11-22"
STATUS = "draft"        # draft | official. Only a reviewed text may say official.

ATTRIBUTION_LINE = "Edited with ClutchClips 🎮"

SECTIONS: list[dict] = [
    {"id": "entry", "title": "How to enter", "needs_legal_review": False, "body": [
        "Entry is free. You need a ClutchClips account with a verified email address. No plan or purchase is needed, and paying for a plan does not improve your chances.",
        "Make your clip with ClutchClips, publish it publicly on TikTok, YouTube Shorts or Instagram Reels, and submit the link to the published video here.",
        "One clip per creator per competition. A video can be entered once.",
        "The video must stay public until the winners are verified.",
    ]},
    {"id": "attribution", "title": "Attribution", "needs_legal_review": False, "body": [
        "Your video's description must include the official ClutchClips link shown on the entry form.",
        "You confirm this when you enter. We check entries by hand and may reject an entry that does not carry the link.",
    ]},
    {"id": "ranking", "title": "Ranking", "needs_legal_review": False, "body": [
        "Approved entries are ranked by the view count shown publicly on the platform.",
        "For now our team reads each count from the video's public page by hand and records when it was read. These counts are unverified and can lag behind the platform.",
        "Ties go to the entry submitted first.",
        "Counts you report yourself are never used.",
    ]},
    {"id": "dates", "title": "Dates and deadlines", "needs_legal_review": True, "body": [
        "Each competition shows its start and end time on this page. Entries are accepted only between them, by our server's clock.",
        "[PLACEHOLDER FOR LEGAL REVIEW: the time zone that governs, the date of the final view count, and when winners are announced.]",
    ]},
    {"id": "eligibility", "title": "Eligibility and age", "needs_legal_review": True, "body": [
        "[PLACEHOLDER FOR LEGAL REVIEW: minimum age, parental consent for minors, and who may not enter (for example employees and their families).]",
    ]},
    {"id": "geography", "title": "Where you can enter from", "needs_legal_review": True, "body": [
        "[PLACEHOLDER FOR LEGAL REVIEW: the countries and regions where entry is open, and where it is void.]",
    ]},
    {"id": "prizes", "title": "Prizes", "needs_legal_review": True, "body": [
        "Prizes, when there are any, are shown on this page for each competition. Prizes are announced when the official rules are published.",
        "No prize is sent automatically. A winner is paid only after a person on our team has verified the entry.",
        "[PLACEHOLDER FOR LEGAL REVIEW: the prize descriptions and values, how and when prizes are delivered, taxes, and what happens to an unclaimed prize.]",
    ]},
    {"id": "winners", "title": "Winner verification", "needs_legal_review": True, "body": [
        "The leaderboard is provisional until our team has reviewed the top entries and approved the winners.",
        "[PLACEHOLDER FOR LEGAL REVIEW: what a winner must provide to be verified, the time allowed to respond, and how an alternate winner is chosen.]",
    ]},
    {"id": "disqualification", "title": "Rejection and disqualification", "needs_legal_review": True, "body": [
        "We may reject or disqualify an entry that breaks these rules, was not made with ClutchClips, lacks the attribution link, is no longer public, uses purchased or artificial views, or infringes someone else's rights. You are told the reason.",
        "[PLACEHOLDER FOR LEGAL REVIEW: the full disqualification procedure and how to dispute a decision.]",
    ]},
    {"id": "platforms", "title": "TikTok, YouTube and Instagram", "needs_legal_review": True, "body": [
        "Creators League is run by ClutchClips. It is not sponsored, endorsed or administered by, or associated with, TikTok, YouTube, Google, Instagram or Meta.",
        "[PLACEHOLDER FOR LEGAL REVIEW: each platform's promotion requirements and the release each requires.]",
    ]},
    {"id": "privacy", "title": "What we show publicly", "needs_legal_review": True, "body": [
        "When you enter, your creator username, avatar, game, your clip's thumbnail, the link to your published video and its public view count appear on the public leaderboard. Your email address and the rest of your account are never shown.",
        "[PLACEHOLDER FOR LEGAL REVIEW: consent to use a winner's name and clip in promotion, and how entry data is kept and deleted.]",
    ]},
    {"id": "law", "title": "Legal", "needs_legal_review": True, "body": [
        "[PLACEHOLDER FOR LEGAL REVIEW: the sponsor's legal name and address, governing law, limitation of liability, and any registration or bonding a prize competition needs where it is offered.]",
    ]},
]


def attribution(public_web_url: str) -> dict:
    """The line a creator pastes into the video's description. The link is this deployment's own website."""
    url = public_web_url.rstrip("/")
    return {"url": url, "text": f"{ATTRIBUTION_LINE}\n{url}"}


def document() -> dict:
    return {"version": VERSION, "status": STATUS, "legally_reviewed": False, "sections": SECTIONS}
