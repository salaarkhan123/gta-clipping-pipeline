"""TikTok Content Posting API (Direct Post). Official OAuth only. Private until audit."""
from __future__ import annotations

from urllib.parse import urlencode

import httpx

from ...config import get_settings
from .base import AdapterResult, register

AUTH = "https://www.tiktok.com/v2/auth/authorize"
TOKEN = "https://open.tiktokapis.com/v2/oauth/token/"
API = "https://open.tiktokapis.com/v2"
SCOPES = ("user.info.basic", "video.publish")


@register("tiktok")
class TikTokAdapter:
    platform = "tiktok"

    def __init__(self, client: httpx.Client | None = None):
        self.http = client or httpx.Client(timeout=60.0)

    def _creds(self):
        s = get_settings()
        return s.tiktok_client_id, s.tiktok_client_secret

    def authorize_url(self, redirect_uri: str, state: str, code_challenge: str) -> str:
        cid, _ = self._creds()
        return AUTH + "?" + urlencode({
            "client_key": cid, "scope": ",".join(SCOPES), "response_type": "code",
            "redirect_uri": redirect_uri, "state": state,
            "code_challenge": code_challenge, "code_challenge_method": "S256",
        })

    def exchange_code(self, code: str, redirect_uri: str, code_verifier: str | None = None) -> dict:
        cid, secret = self._creds()
        r = self.http.post(TOKEN, data={
            "client_key": cid, "client_secret": secret, "code": code,
            "grant_type": "authorization_code", "redirect_uri": redirect_uri,
            **({"code_verifier": code_verifier} if code_verifier else {}),
        })
        r.raise_for_status()
        tok = r.json()
        return {
            "access_token": tok["access_token"], "refresh_token": tok.get("refresh_token"),
            "expires_in": tok.get("expires_in"), "refresh_expires_in": tok.get("refresh_expires_in"),
            "scopes": (tok.get("scope") or " ".join(SCOPES)).replace(",", " ").split(),
            "external_id": str(tok.get("open_id") or "unknown"),
            "display_name": "TikTok", "avatar_url": None,
        }

    def refresh(self, refresh_token: str) -> dict:
        cid, secret = self._creds()
        r = self.http.post(TOKEN, data={
            "client_key": cid, "client_secret": secret,
            "grant_type": "refresh_token", "refresh_token": refresh_token,
        })
        r.raise_for_status()
        tok = r.json()
        return {
            "access_token": tok["access_token"],
            "refresh_token": tok.get("refresh_token", refresh_token),
            "expires_in": tok.get("expires_in"),
            "refresh_expires_in": tok.get("refresh_expires_in"),
            "scopes": (tok.get("scope") or " ".join(SCOPES)).replace(",", " ").split(),
        }

    def revoke(self, access_token: str) -> None:
        cid, secret = self._creds()
        try:
            self.http.post(f"{API}/oauth/revoke/", data={
                "client_key": cid, "client_secret": secret, "token": access_token,
            }, timeout=10.0)
        except httpx.HTTPError:
            pass

    def publish(
        self, *, access_token: str, media_path: str | None, media_url: str | None,
        title: str | None, caption: str, privacy: str | None, options: dict,
        step: str | None, external_ref: str | None,
    ) -> AdapterResult:
        if step == "published" and external_ref:
            return self.status(access_token=access_token, external_ref=external_ref)
        if not media_url:
            return AdapterResult(ok=False, error_code="export_required",
                                 error_message="TikTok requires PULL_FROM_URL under a verified domain.",
                                 retryable=False)
        if not privacy:
            return AdapterResult(ok=False, error_code="validation_rejected",
                                 error_message="TikTok requires an explicit privacy choice (no default).",
                                 retryable=False)
        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
        init = self.http.post(f"{API}/post/publish/video/init/", headers=headers, json={
            "post_info": {
                "title": (caption or title or "")[:2200],
                "privacy_level": privacy,
                "disable_comment": bool(options.get("disable_comment", True)),
                "disable_duet": bool(options.get("disable_duet", True)),
                "disable_stitch": bool(options.get("disable_stitch", True)),
            },
            "source_info": {"source": "PULL_FROM_URL", "video_url": media_url},
        })
        if init.status_code >= 500 or init.status_code == 429:
            return AdapterResult(ok=False, error_code="platform_unavailable",
                                 error_message=f"TikTok init {init.status_code}", retryable=True)
        if init.status_code >= 400:
            return AdapterResult(ok=False, error_code="validation_rejected",
                                 error_message=(init.text or "")[:400], retryable=False)
        data = (init.json() or {}).get("data") or {}
        pub_id = data.get("publish_id")
        if not pub_id:
            return AdapterResult(ok=False, error_code="platform_unavailable",
                                 error_message="TikTok did not return publish_id.", retryable=True)
        # Finalizing is the init for Direct Post pull; status poll completes it — do not re-init.
        return AdapterResult(ok=True, step="published", external_ref=pub_id, external_id=pub_id,
                             data={"awaiting_processing": True})

    def status(self, *, access_token: str, external_ref: str) -> AdapterResult:
        r = self.http.post(f"{API}/post/publish/status/fetch/",
                           headers={"Authorization": f"Bearer {access_token}",
                                    "Content-Type": "application/json"},
                           json={"publish_id": external_ref})
        if r.status_code >= 400:
            return AdapterResult(ok=False, error_code="outcome_unknown",
                                 error_message=(r.text or "")[:400], retryable=False)
        st = ((r.json() or {}).get("data") or {}).get("status")
        if st in ("PUBLISH_COMPLETE", "COMPLETE"):
            return AdapterResult(ok=True, step="published", external_ref=external_ref,
                                 external_id=external_ref)
        if st in ("FAILED", "PUBLISH_FAILED"):
            return AdapterResult(ok=False, error_code="validation_rejected",
                                 error_message="TikTok rejected the video.", retryable=False)
        return AdapterResult(ok=True, step="processing", external_ref=external_ref,
                             data={"status": st})
