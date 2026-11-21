"""Instagram Reels via Instagram Platform content publishing (Instagram Login)."""
from __future__ import annotations

from urllib.parse import urlencode

import httpx

from ...config import get_settings
from .base import AdapterResult, register

GRAPH = "https://graph.instagram.com"
AUTH = "https://api.instagram.com/oauth/authorize"
TOKEN = "https://api.instagram.com/oauth/access_token"
SCOPES = ("instagram_business_basic", "instagram_business_content_publish")


@register("instagram")
class InstagramAdapter:
    platform = "instagram"

    def __init__(self, client: httpx.Client | None = None):
        self.http = client or httpx.Client(timeout=60.0)

    def _creds(self):
        s = get_settings()
        return s.instagram_client_id, s.instagram_client_secret

    def authorize_url(self, redirect_uri: str, state: str, code_challenge: str) -> str:
        cid, _ = self._creds()
        return AUTH + "?" + urlencode({
            "client_id": cid, "redirect_uri": redirect_uri, "scope": ",".join(SCOPES),
            "response_type": "code", "state": state,
        })

    def exchange_code(self, code: str, redirect_uri: str, code_verifier: str | None = None) -> dict:
        cid, secret = self._creds()
        r = self.http.post(TOKEN, data={
            "client_id": cid, "client_secret": secret, "grant_type": "authorization_code",
            "redirect_uri": redirect_uri, "code": code,
        })
        r.raise_for_status()
        short = r.json()
        long = self.http.get(f"{GRAPH}/access_token", params={
            "grant_type": "ig_exchange_token", "client_secret": secret,
            "access_token": short["access_token"],
        })
        long.raise_for_status()
        tok = long.json()
        me = self.http.get(f"{GRAPH}/me", params={
            "fields": "user_id,username", "access_token": tok["access_token"],
        })
        me.raise_for_status()
        profile = me.json()
        return {
            "access_token": tok["access_token"], "refresh_token": None,
            "expires_in": tok.get("expires_in"),
            "scopes": list(SCOPES),
            "external_id": str(profile.get("user_id") or profile.get("id") or "unknown"),
            "display_name": profile.get("username") or "Instagram",
            "avatar_url": None,
        }

    def refresh(self, refresh_token: str) -> dict:
        # Instagram long-lived tokens refresh via the access token itself.
        r = self.http.get(f"{GRAPH}/refresh_access_token", params={
            "grant_type": "ig_refresh_token", "access_token": refresh_token,
        })
        r.raise_for_status()
        tok = r.json()
        return {
            "access_token": tok["access_token"], "refresh_token": tok["access_token"],
            "expires_in": tok.get("expires_in"), "scopes": list(SCOPES),
        }

    def revoke(self, access_token: str) -> None:
        return  # Meta has no simple revoke for IG user tokens; disconnect deletes locally.

    def publish(
        self, *, access_token: str, media_path: str | None, media_url: str | None,
        title: str | None, caption: str, privacy: str | None, options: dict,
        step: str | None, external_ref: str | None,
    ) -> AdapterResult:
        if step == "published" and external_ref:
            return AdapterResult(ok=True, step="published", external_ref=external_ref,
                                 external_id=external_ref)
        if step == "container" and external_ref:
            return self._publish_container(access_token, external_ref)
        if not media_url:
            return AdapterResult(ok=False, error_code="export_required",
                                 error_message="Instagram pulls the export from a public URL.",
                                 retryable=False)
        me = self.http.get(f"{GRAPH}/me", params={"fields": "user_id", "access_token": access_token})
        if me.status_code >= 400:
            return AdapterResult(ok=False, error_code="reconnect_required",
                                 error_message=(me.text or "")[:400], retryable=False)
        ig_id = (me.json() or {}).get("user_id") or (me.json() or {}).get("id")
        create = self.http.post(f"{GRAPH}/{ig_id}/media", params={
            "media_type": "REELS", "video_url": media_url, "caption": caption or "",
            "access_token": access_token,
        })
        if create.status_code >= 500 or create.status_code == 429:
            return AdapterResult(ok=False, error_code="platform_unavailable",
                                 error_message=f"Instagram container {create.status_code}", retryable=True)
        if create.status_code >= 400:
            return AdapterResult(ok=False, error_code="validation_rejected",
                                 error_message=(create.text or "")[:400], retryable=False)
        container = (create.json() or {}).get("id")
        if not container:
            return AdapterResult(ok=False, error_code="platform_unavailable",
                                 error_message="Instagram did not return a container id.", retryable=True)
        return self._publish_container(access_token, container, ig_id=ig_id)

    def _publish_container(self, access_token: str, container: str, ig_id: str | None = None) -> AdapterResult:
        # Poll container readiness briefly; worker will re-enter if still processing.
        st = self.http.get(f"{GRAPH}/{container}", params={
            "fields": "status_code", "access_token": access_token,
        })
        code = ((st.json() or {}).get("status_code") or "").upper() if st.status_code < 400 else ""
        if code in ("IN_PROGRESS", "PUBLISHED"):
            if code == "PUBLISHED":
                return AdapterResult(ok=True, step="published", external_ref=container, external_id=container)
            return AdapterResult(ok=True, step="container", external_ref=container,
                                 data={"awaiting_processing": True})
        if code == "ERROR":
            return AdapterResult(ok=False, error_code="validation_rejected",
                                 error_message="Instagram rejected the reel.", retryable=False)
        if not ig_id:
            me = self.http.get(f"{GRAPH}/me", params={"fields": "user_id", "access_token": access_token})
            ig_id = (me.json() or {}).get("user_id") or (me.json() or {}).get("id")
        # Final publish call — at most once. On lost answer, status-check container.
        pub = self.http.post(f"{GRAPH}/{ig_id}/media_publish", params={
            "creation_id": container, "access_token": access_token,
        })
        if pub.status_code in (408,) or (pub.status_code == 0):
            return AdapterResult(ok=False, step="container", external_ref=container,
                                 error_code="outcome_unknown",
                                 error_message="Publish response lost; check Instagram before retrying.",
                                 retryable=False)
        if pub.status_code >= 500 or pub.status_code == 429:
            return AdapterResult(ok=False, step="container", external_ref=container,
                                 error_code="platform_unavailable",
                                 error_message=f"Instagram publish {pub.status_code}", retryable=True)
        if pub.status_code >= 400:
            return AdapterResult(ok=False, error_code="validation_rejected",
                                 error_message=(pub.text or "")[:400], retryable=False)
        mid = (pub.json() or {}).get("id") or container
        return AdapterResult(ok=True, step="published", external_ref=mid, external_id=mid)

    def status(self, *, access_token: str, external_ref: str) -> AdapterResult:
        r = self.http.get(f"{GRAPH}/{external_ref}", params={
            "fields": "status_code", "access_token": access_token,
        })
        if r.status_code >= 400:
            return AdapterResult(ok=False, error_code="outcome_unknown",
                                 error_message=(r.text or "")[:400], retryable=False)
        code = ((r.json() or {}).get("status_code") or "").upper()
        if code == "FINISHED" or code == "PUBLISHED":
            return AdapterResult(ok=True, step="published", external_ref=external_ref,
                                 external_id=external_ref)
        if code == "ERROR":
            return AdapterResult(ok=False, error_code="validation_rejected",
                                 error_message="Instagram rejected the reel.", retryable=False)
        return AdapterResult(ok=True, step="container", external_ref=external_ref,
                             data={"status": code})
