"""Google Gemini Nano Banana 2.1: image edit through the Interactions API (primary provider for premium thumbnails).

Request format from https://aistudio.google.com/docs/image-generation (read 2026-11-17): POST
/v1beta/interactions with `x-goog-api-key` and `Api-Revision: 2026-05-20`; `input` is a list of content blocks
({"type": "text"} and {"type": "image", "mime_type", "data": base64}); `response_format` {"type": "image",
"aspect_ratio", "image_size": "1K" | "2K" | "4K"}. 9:16 at 2K is 1536x2752. The picture comes back as an
{"type": "image", "data"} block inside `steps[].content` of a `model_output` step. Status and usage names are
from https://aistudio.google.com/api-reference/interactions-api (`status`: completed | failed | incomplete | ...;
`errors[]`; `usage.total_input_tokens`, `usage.output_tokens_by_modality[{modality, tokens}]`).

Cost (https://aistudio.google.com/docs/pricing, standard tier, read 2026-11-17): input $1.50 per 1M tokens, image
output $30 per 1M tokens ($0.0504 per 2K image), text and thinking output $7.50 per 1M tokens.
"""
import base64

import httpx

from .base import MAX_IMAGE_BYTES, NO_IMAGE, PROVIDER_ERROR, SAFETY, TIMEOUT, EditRequest, EditResult, ProviderFailed

URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
API_REVISION = "2026-05-20"
INPUT_PER_TOKEN = 1.50 / 1e6
IMAGE_OUT_PER_TOKEN = 30.0 / 1e6
TEXT_OUT_PER_TOKEN = 7.50 / 1e6
PER_IMAGE = {"1K": 0.0336, "2K": 0.0504, "4K": 0.113}     # the published price, when usage is missing
SAFETY_WORDS = ("safety", "blocked", "prohibited", "policy", "responsible ai", "image_safety")


def cost_of(usage: dict, size: str) -> tuple[float | None, str]:
    """(dollars, how it was worked out) for one call from its usage figures."""
    if not isinstance(usage, dict) or "total_input_tokens" not in usage:
        price = PER_IMAGE.get(size)
        return price, "published per-image price (no usage in the answer)" if price is not None else ""
    by = {m.get("modality"): int(m.get("tokens") or 0) for m in usage.get("output_tokens_by_modality") or []
          if isinstance(m, dict)}
    image_out = by.get("image", 0)
    other_out = max(0, int(usage.get("total_output_tokens") or 0) - image_out) + int(usage.get("total_thought_tokens") or 0)
    dollars = (int(usage.get("total_input_tokens") or 0) * INPUT_PER_TOKEN + image_out * IMAGE_OUT_PER_TOKEN
               + other_out * TEXT_OUT_PER_TOKEN)
    return round(dollars, 6), "usage tokens x published price"


def _safety(text: str) -> bool:
    low = text.lower()
    return any(w in low for w in SAFETY_WORDS)


class GeminiEditor:
    name = "gemini"

    def __init__(self, api_key: str, model: str = "gemini-nano-banana-2.1", size: str = "2K", transport=None):
        self.api_key, self.model, self.size, self.transport = api_key, model, size, transport

    def body(self, request: EditRequest) -> dict:
        blocks = [{"type": "text", "text": request.prompt},
                  {"type": "image", "mime_type": "image/jpeg", "data": base64.b64encode(request.frame).decode()}]
        if request.reference:
            blocks.append({"type": "image", "mime_type": "image/jpeg",
                           "data": base64.b64encode(request.reference).decode()})
        return {"model": self.model, "input": blocks, "store": False,
                "response_format": {"type": "image", "mime_type": "image/jpeg", "aspect_ratio": request.aspect,
                                    "image_size": self.size}}

    def edit(self, request: EditRequest, timeout: float) -> EditResult:
        headers = {"x-goog-api-key": self.api_key, "Content-Type": "application/json", "Api-Revision": API_REVISION}
        try:
            with httpx.Client(timeout=httpx.Timeout(timeout, connect=10.0), transport=self.transport,
                              follow_redirects=False) as client:
                resp = client.post(URL, json=self.body(request), headers=headers)
        except httpx.TimeoutException:
            raise ProviderFailed(TIMEOUT, f"Gemini did not answer within {timeout:.0f} s.") from None
        except httpx.HTTPError as e:
            raise ProviderFailed(PROVIDER_ERROR, f"Gemini could not be reached ({type(e).__name__}).") from None
        if len(resp.content) > MAX_IMAGE_BYTES * 2:
            raise ProviderFailed(PROVIDER_ERROR, "Gemini's answer was too large.")
        try:
            data = resp.json()
        except ValueError:
            data = {}
        data = data if isinstance(data, dict) else {}
        if resp.status_code >= 400:
            err = data.get("error")
            message = str(err.get("message")) if isinstance(err, dict) and err.get("message") else resp.text[:200]
            code = SAFETY if resp.status_code == 400 and _safety(message) else PROVIDER_ERROR
            raise ProviderFailed(code, f"Gemini answered {resp.status_code}: {message[:200]}")
        cost, source = cost_of(data.get("usage") or {}, self.size)
        status = str(data.get("status") or "")
        errors = " ".join(str(e.get("message") or e.get("code") or "") for e in data.get("errors") or []
                          if isinstance(e, dict))
        image = _first_image(data)
        if image is None:
            texts = " ".join(_texts(data))
            if status == "failed" and not _safety(errors):
                raise ProviderFailed(PROVIDER_ERROR, f"Gemini failed: {errors[:200] or 'no reason given'}", cost)
            if _safety(errors) or _safety(texts) or status == "incomplete":
                raise ProviderFailed(SAFETY, f"Gemini returned no image ({status or 'no status'}): "
                                             f"{(errors or texts)[:200] or 'blocked'}", cost)
            raise ProviderFailed(NO_IMAGE, f"Gemini returned no image ({status or 'no status'}).", cost)
        raw, mime = image
        try:
            picture = base64.b64decode(raw, validate=False)
        except (ValueError, TypeError):
            raise ProviderFailed(PROVIDER_ERROR, "Gemini's image could not be read.", cost) from None
        if not picture or len(picture) > MAX_IMAGE_BYTES:
            raise ProviderFailed(PROVIDER_ERROR, "Gemini's image was empty or too large.", cost)
        return EditResult(picture, mime or "image/jpeg", self.name, self.model, cost, source,
                          {"usage": data.get("usage"), "status": status})


def _blocks(data: dict):
    for step in data.get("steps") or []:
        if isinstance(step, dict):
            for block in step.get("content") or []:
                if isinstance(block, dict):
                    yield block
    for block in data.get("outputs") or []:          # older answer shape
        if isinstance(block, dict):
            yield block


def _first_image(data: dict) -> tuple[str, str] | None:
    for block in _blocks(data):
        if block.get("type") == "image" and isinstance(block.get("data"), str) and block["data"]:
            return block["data"], str(block.get("mime_type") or "")
    return None


def _texts(data: dict) -> list[str]:
    return [str(b.get("text")) for b in _blocks(data) if b.get("type") == "text" and b.get("text")]
