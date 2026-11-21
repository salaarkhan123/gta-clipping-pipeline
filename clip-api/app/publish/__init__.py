"""Social publishing: connect accounts, publish or schedule clips, track status.

Behind PUBLISHING (off by default). Official platform APIs and OAuth only. Tokens never leave the API.
See docs/publishing.md. No real posts without owner authorization.
"""

PLATFORMS = ("youtube", "tiktok", "instagram", "facebook")  # X and LinkedIn held (pricing / terms)
POST_STATUSES = (
    "SCHEDULED", "QUEUED", "UPLOADING", "PROCESSING", "PUBLISHED", "FAILED", "CANCELED",
)
ACCOUNT_STATUSES = ("active", "needs_reconnect", "revoked")
# Terminal for cancel/edit rules; retries only from FAILED with a safe class.
TERMINAL = frozenset({"PUBLISHED", "FAILED", "CANCELED"})
EDITABLE = frozenset({"SCHEDULED"})
CLAIMABLE = frozenset({"SCHEDULED", "QUEUED"})
ACTIVE_UPLOAD = frozenset({"QUEUED", "UPLOADING", "PROCESSING"})
