"""What every image-edit provider takes and gives back, and how it fails.

A provider is one small module (gemini.py) with one class that has `name`, `model` and
`edit(request, timeout) -> EditResult`. It never touches the database, storage or credits, and it raises
ProviderFailed for every way a call can go wrong, so the caller can retry on the next provider and refund.
"""
from dataclasses import dataclass, field
from typing import Protocol

# Why a call failed. Every one ends in the next provider (once) and then in a full refund.
PROVIDER_ERROR = "provider_error"      # HTTP error, bad answer, provider down
TIMEOUT = "provider_timeout"           # no image within the timeout
SAFETY = "safety_block"                # the provider refused the request or its output
NO_IMAGE = "no_image"                  # an answer without a picture in it
FACE_LOST = "face_lost"                # our check: the streamer's face is gone from the output

MAX_IMAGE_BYTES = 25 * 1024 * 1024     # a provider answer bigger than this is refused


class ProviderFailed(Exception):
    def __init__(self, code: str, message: str, cost_usd: float | None = None):
        super().__init__(message)
        self.code, self.message, self.cost_usd = code, message, cost_usd


@dataclass
class EditRequest:
    prompt: str
    frame: bytes                       # JPEG: the clip's thumbnail frame, without text
    aspect: str                        # "9:16", "4:5", "1:1" or "16:9"
    reference: bytes | None = None     # JPEG: a close-up of the streamer's face from the same frame


@dataclass
class EditResult:
    image: bytes
    mime: str
    provider: str
    model: str
    cost_usd: float | None = None      # what this call cost, from its usage figures (see each provider)
    cost_source: str = ""
    usage: dict = field(default_factory=dict)


class ImageEditor(Protocol):
    name: str
    model: str

    def edit(self, request: EditRequest, timeout: float) -> EditResult: ...
