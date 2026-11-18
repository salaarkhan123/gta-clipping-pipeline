"""Black Forest Labs FLUX.1 Kontext [pro]: image edit (the fallback provider for premium thumbnails).

Request format from https://docs.bfl.ai/kontext/kontext_image_editing (read 2026-11-17): POST
https://api.bfl.ai/v1/flux-kontext-pro with `x-key`; body `prompt`, `input_image` (base64), `aspect_ratio`
(3:7 to 7:3), `output_format`, `safety_tolerance` (0 strictest to 6), `prompt_upsampling`. It answers `id` and
`polling_url`; GET the polling URL with `x-key` about every 0.5 s until `status` is `Ready` (the picture's signed
URL, valid 10 minutes, is `result.sample`). Moderated, error and failed statuses end the call. Output is about
1 MP (about 768x1344 at 9:16). Only one input image is documented, so the face close-up is not sent.

Cost: $0.04 per image flat (https://bfl.ai/pricing, read 2026-11-17).
"""
import base64
import time
from urllib.parse import urlparse

import httpx

from .base import MAX_IMAGE_BYTES, PROVIDER_ERROR, SAFETY, TIMEOUT, EditRequest, EditResult, ProviderFailed

URL = "https://api.bfl.ai/v1/flux-kontext-pro"
PRICE = 0.04
POLL_SEC = 0.5
SAFETY_TOLERANCE = 2                    # BFL's default
FAILED = {"Error", "Failed", "Task not found"}


def _bfl_https(url: str) -> bool:
    """Polling and result URLs come from the answer: only BFL's own https hosts are followed."""
    u = urlparse(url)
    host = (u.hostname or "").lower()
    return u.scheme == "https" and (host == "bfl.ai" or host.endswith(".bfl.ai"))


class BflEditor:
    name = "bfl"
    model = "flux-kontext-pro"

    def __init__(self, api_key: str, transport=None, sleep=time.sleep, clock=time.monotonic):
        self.api_key, self.transport, self.sleep, self.clock = api_key, transport, sleep, clock

    def body(self, request: EditRequest) -> dict:
        return {"prompt": request.prompt, "input_image": base64.b64encode(request.frame).decode(),
                "aspect_ratio": request.aspect, "output_format": "jpeg", "safety_tolerance": SAFETY_TOLERANCE,
                "prompt_upsampling": False}

    def edit(self, request: EditRequest, timeout: float) -> EditResult:
        end = self.clock() + timeout
        headers = {"x-key": self.api_key, "accept": "application/json", "Content-Type": "application/json"}
        try:
            with httpx.Client(timeout=httpx.Timeout(min(timeout, 30.0), connect=10.0), transport=self.transport,
                              follow_redirects=False) as client:
                resp = client.post(URL, json=self.body(request), headers=headers)
                if resp.status_code >= 400:
                    raise ProviderFailed(PROVIDER_ERROR, f"BFL answered {resp.status_code}: {resp.text[:200]}")
                task = _json(resp)
                poll = str(task.get("polling_url") or "")
                if not _bfl_https(poll):
                    raise ProviderFailed(PROVIDER_ERROR, "BFL gave no usable polling URL.")
                while True:
                    if self.clock() > end:
                        raise ProviderFailed(TIMEOUT, f"BFL did not finish within {timeout:.0f} s.")
                    self.sleep(POLL_SEC)
                    got = client.get(poll, headers={"x-key": self.api_key, "accept": "application/json"})
                    if got.status_code >= 400:
                        raise ProviderFailed(PROVIDER_ERROR, f"BFL polling answered {got.status_code}.")
                    state = _json(got)
                    status = str(state.get("status") or "")
                    if status == "Ready":
                        break
                    if "Moderated" in status:
                        raise ProviderFailed(SAFETY, f"BFL refused the request ({status}).")
                    if status in FAILED:
                        raise ProviderFailed(PROVIDER_ERROR, f"BFL failed ({status}).")
                sample = str((state.get("result") or {}).get("sample") or "")
                if not _bfl_https(sample):
                    raise ProviderFailed(PROVIDER_ERROR, "BFL gave no usable image URL.")
                picture = client.get(sample)
                if picture.status_code >= 400 or not picture.content or len(picture.content) > MAX_IMAGE_BYTES:
                    raise ProviderFailed(PROVIDER_ERROR, "BFL's image could not be downloaded.")
        except httpx.TimeoutException:
            raise ProviderFailed(TIMEOUT, f"BFL did not answer within {timeout:.0f} s.") from None
        except httpx.HTTPError as e:
            raise ProviderFailed(PROVIDER_ERROR, f"BFL could not be reached ({type(e).__name__}).") from None
        return EditResult(picture.content, picture.headers.get("content-type", "image/jpeg"), self.name, self.model,
                          PRICE, "published price per image", {"id": task.get("id"), "status": status})


def _json(resp) -> dict:
    try:
        data = resp.json()
    except ValueError:
        raise ProviderFailed(PROVIDER_ERROR, "BFL's answer could not be read.") from None
    if not isinstance(data, dict):
        raise ProviderFailed(PROVIDER_ERROR, "BFL's answer could not be read.")
    return data
