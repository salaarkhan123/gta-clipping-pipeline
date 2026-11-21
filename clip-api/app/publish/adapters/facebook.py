"""Facebook Reels Publishing API (Pages only)."""
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlencode

import httpx

from ...config import get_settings
from .base import AdapterResult, register

GRAPH = "https://graph.facebook.com/v21.0"
AUTH = "https://www.facebook.com/v21.0/dialog/oauth"
TOKEN = "https://graph.facebook.com/v21.0/oauth/access_token"
SCOPES = ("pages_show_list", "pages_read_engagement", "pages_manage_posts")


@register("facebook")
class FacebookAdapter:
    platform = "facebook"

    def __init__(self, client: httpx.Client | None = None):
        self.http = client or httpx.Client(timeout=60.0)

    def _creds(self):
        s = get_settings()
        return s.facebook_client_id, s.facebook_client_secret

    def authorize_url(self, redirect_uri: str, state: str, code_challenge: str) -> str:
        cid, _ = self._creds()
        return AUTH + "?" + urlencode({
            "client_id": cid, "redirect_uri": redirect_uri, "state": state,
            "scope": ",".join(SCOPES), "response_type": "code",
        })

    def exchange_code(self, code: str, redirect_uri: str, code_verifier: str | None = None) -> dict:
        cid, secret = self._creds()
        r = self.http.get(TOKEN, params={
            "client_id": cid, "client_secret": secret, "redirect_uri": redirect_uri, "code": code,
        })
        r.raise_for_status()
        user_tok = r.json()["access_token"]
        pages = self.http.get(f"{GRAPH}/me/accounts", params={"access_token": user_tok})
        pages.raise_for_status()
        data = (pages.json() or {}).get("data") or []
        if not data:
            raise httpx.HTTPError("No Facebook Pages available to publish Reels")
        page = data[0]
        return {
            "access_token": page["access_token"], "refresh_token": user_tok,
            "expires_in": None, "scopes": list(SCOPES),
            "external_id": str(page["id"]),
            "display_name": page.get("name") or "Facebook Page",
            "avatar_url": None,
        }

    def refresh(self, refresh_token: str) -> dict:
        cid, secret = self._creds()
        r = self.http.get(TOKEN, params={
            "grant_type": "fb_exchange_token", "client_id": cid, "client_secret": secret,
            "fb_exchange_token": refresh_token,
        })
        r.raise_for_status()
        tok = r.json()
        return {
            "access_token": tok["access_token"], "refresh_token": tok["access_token"],
            "expires_in": tok.get("expires_in"), "scopes": list(SCOPES),
        }

    def revoke(self, access_token: str) -> None:
        try:
            self.http.delete(f"{GRAPH}/me/permissions", params={"access_token": access_token}, timeout=10.0)
        except httpx.HTTPError:
            pass

    def publish(
        self, *, access_token: str, media_path: str | None, media_url: str | None,
        title: str | None, caption: str, privacy: str | None, options: dict,
        step: str | None, external_ref: str | None,
    ) -> AdapterResult:
        if step == "published" and external_ref:
            return AdapterResult(ok=True, step="published", external_ref=external_ref,
                                 external_id=external_ref)
        page_id = options.get("page_id")
        if not page_id:
            return AdapterResult(ok=False, error_code="validation_rejected",
                                 error_message="Facebook Reels need a Page id.", retryable=False)
        if not media_path and not media_url:
            return AdapterResult(ok=False, error_code="export_required",
                                 error_message="Facebook needs export bytes or a URL.", retryable=False)

        start = self.http.post(f"{GRAPH}/{page_id}/video_reels", params={
            "upload_phase": "start", "access_token": access_token,
        })
        if start.status_code >= 500 or start.status_code == 429:
            return AdapterResult(ok=False, error_code="platform_unavailable",
                                 error_message=f"Facebook start {start.status_code}", retryable=True)
        if start.status_code >= 400:
            return AdapterResult(ok=False, error_code="validation_rejected",
                                 error_message=(start.text or "")[:400], retryable=False)
        video_id = (start.json() or {}).get("video_id")
        upload_url = (start.json() or {}).get("upload_url")
        if not video_id or not upload_url:
            return AdapterResult(ok=False, error_code="platform_unavailable",
                                 error_message="Facebook did not return an upload session.", retryable=True)

        if media_path:
            size = Path(media_path).stat().st_size
            with open(media_path, "rb") as fh:
                up = self.http.post(upload_url, headers={
                    "Authorization": f"OAuth {access_token}",
                    "offset": "0", "file_size": str(size),
                }, content=fh)
            if up.status_code >= 500 or up.status_code == 429:
                return AdapterResult(ok=False, step="session", external_ref=video_id,
                                     error_code="platform_unavailable",
                                     error_message=f"Facebook upload {up.status_code}", retryable=True)
            if up.status_code >= 400:
                return AdapterResult(ok=False, error_code="validation_rejected",
                                     error_message=(up.text or "")[:400], retryable=False)

        # Final finish call — at most once.
        finish = self.http.post(f"{GRAPH}/{page_id}/video_reels", params={
            "upload_phase": "finish", "video_id": video_id,
            "video_state": "PUBLISHED", "description": caption or title or "",
            "access_token": access_token,
        })
        if finish.status_code in (408,):
            return AdapterResult(ok=False, step="session", external_ref=video_id,
                                 error_code="outcome_unknown",
                                 error_message="Finish response lost; check the Page before retrying.",
                                 retryable=False)
        if finish.status_code >= 500 or finish.status_code == 429:
            return AdapterResult(ok=False, step="session", external_ref=video_id,
                                 error_code="platform_unavailable",
                                 error_message=f"Facebook finish {finish.status_code}", retryable=True)
        if finish.status_code >= 400:
            return AdapterResult(ok=False, error_code="validation_rejected",
                                 error_message=(finish.text or "")[:400], retryable=False)
        return AdapterResult(ok=True, step="published", external_ref=video_id, external_id=video_id,
                             external_url=f"https://facebook.com/reel/{video_id}")

    def status(self, *, access_token: str, external_ref: str) -> AdapterResult:
        r = self.http.get(f"{GRAPH}/{external_ref}", params={
            "fields": "status", "access_token": access_token,
        })
        if r.status_code >= 400:
            return AdapterResult(ok=False, error_code="outcome_unknown",
                                 error_message=(r.text or "")[:400], retryable=False)
        return AdapterResult(ok=True, step="published", external_ref=external_ref,
                             external_id=external_ref)
