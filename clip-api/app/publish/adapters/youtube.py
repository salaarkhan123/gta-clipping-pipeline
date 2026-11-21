"""YouTube Data API v3 videos.insert (resumable). Official OAuth only."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx

from ...config import get_settings
from .base import AdapterResult, register

AUTH = "https://oauth2.googleapis.com"
API = "https://www.googleapis.com/youtube/v3"
UPLOAD = "https://www.googleapis.com/upload/youtube/v3/videos"
SCOPES = ("https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube.readonly")


@register("youtube")
class YouTubeAdapter:
    platform = "youtube"

    def __init__(self, client: httpx.Client | None = None):
        self.http = client or httpx.Client(timeout=60.0)

    def _creds(self) -> tuple[str, str]:
        s = get_settings()
        return s.youtube_client_id, s.youtube_client_secret

    def authorize_url(self, redirect_uri: str, state: str, code_challenge: str) -> str:
        from urllib.parse import urlencode
        cid, _ = self._creds()
        q = urlencode({
            "client_id": cid,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(SCOPES),
            "access_type": "offline",
            "include_granted_scopes": "true",
            "prompt": "consent",
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        })
        return f"https://accounts.google.com/o/oauth2/v2/auth?{q}"

    def exchange_code(self, code: str, redirect_uri: str, code_verifier: str | None = None) -> dict:
        cid, secret = self._creds()
        body = {
            "code": code, "client_id": cid, "client_secret": secret,
            "redirect_uri": redirect_uri, "grant_type": "authorization_code",
        }
        if code_verifier:
            body["code_verifier"] = code_verifier
        r = self.http.post(f"{AUTH}/token", data=body)
        r.raise_for_status()
        tok = r.json()
        profile = self._channel(tok["access_token"])
        return {
            "access_token": tok["access_token"],
            "refresh_token": tok.get("refresh_token"),
            "expires_in": tok.get("expires_in"),
            "scopes": tok.get("scope", " ".join(SCOPES)).split(),
            **profile,
        }

    def refresh(self, refresh_token: str) -> dict:
        cid, secret = self._creds()
        r = self.http.post(f"{AUTH}/token", data={
            "client_id": cid, "client_secret": secret,
            "refresh_token": refresh_token, "grant_type": "refresh_token",
        })
        r.raise_for_status()
        tok = r.json()
        return {
            "access_token": tok["access_token"],
            "refresh_token": tok.get("refresh_token", refresh_token),
            "expires_in": tok.get("expires_in"),
            "scopes": tok.get("scope", " ".join(SCOPES)).split(),
        }

    def revoke(self, access_token: str) -> None:
        try:
            self.http.post(f"{AUTH}/revoke", data={"token": access_token}, timeout=10.0)
        except httpx.HTTPError:
            pass

    def _channel(self, access_token: str) -> dict:
        r = self.http.get(f"{API}/channels", params={"part": "snippet", "mine": "true"},
                          headers={"Authorization": f"Bearer {access_token}"})
        r.raise_for_status()
        items = r.json().get("items") or []
        if not items:
            return {"external_id": "unknown", "display_name": "YouTube channel", "avatar_url": None}
        ch = items[0]
        sn = ch.get("snippet") or {}
        thumbs = (sn.get("thumbnails") or {}).get("default") or {}
        return {
            "external_id": ch["id"],
            "display_name": sn.get("title") or "YouTube channel",
            "avatar_url": thumbs.get("url"),
        }

    def publish(
        self, *, access_token: str, media_path: str | None, media_url: str | None,
        title: str | None, caption: str, privacy: str | None, options: dict,
        step: str | None, external_ref: str | None,
    ) -> AdapterResult:
        if step == "inserted" and external_ref:
            return self.status(access_token=access_token, external_ref=external_ref)

        if not media_path:
            return AdapterResult(ok=False, error_code="export_required",
                                 error_message="YouTube needs the export file bytes.", retryable=False)

        meta: dict[str, Any] = {
            "snippet": {
                "title": (title or "Untitled clip")[:100],
                "description": caption or "",
                "categoryId": "20",
            },
            "status": {
                "privacyStatus": privacy or "private",
                "selfDeclaredMadeForKids": bool(options.get("made_for_kids", False)),
                "containsSyntheticMedia": bool(options.get("contains_synthetic_media", False)),
            },
        }
        if "paid_product_placement" in options:
            meta["paidProductPlacementDetails"] = {
                "hasPaidProductPlacement": bool(options["paid_product_placement"]),
            }

        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
        size = Path(media_path).stat().st_size
        init = self.http.post(
            UPLOAD,
            params={"uploadType": "resumable", "part": "snippet,status,paidProductPlacementDetails"},
            headers={**headers, "X-Upload-Content-Type": "video/*", "X-Upload-Content-Length": str(size)},
            content=json.dumps(meta),
        )
        if init.status_code >= 500 or init.status_code == 429:
            return AdapterResult(ok=False, error_code="platform_unavailable",
                                 error_message=f"YouTube init {init.status_code}", retryable=True)
        if init.status_code >= 400:
            return AdapterResult(ok=False, error_code="validation_rejected",
                                 error_message=_short(init), retryable=False)
        session = init.headers.get("Location")
        if not session:
            return AdapterResult(ok=False, error_code="platform_unavailable",
                                 error_message="YouTube did not return an upload session.", retryable=True)

        # Transfer: retryable. Final response creates the video — treat as at-most-once.
        with open(media_path, "rb") as fh:
            put = self.http.put(session, content=fh, headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "video/*",
                "Content-Length": str(size),
            })
        if put.status_code in (500, 502, 503, 504) or put.status_code == 429:
            return AdapterResult(ok=False, step="session", external_ref=session,
                                 error_code="platform_unavailable",
                                 error_message=f"YouTube upload {put.status_code}", retryable=True)
        if put.status_code >= 400:
            # Lost answer on final call: do not repeat blindly — caller should status-check if we had an id.
            if put.status_code in (408, 499) or put.request is None:
                return AdapterResult(ok=False, step="session", external_ref=session,
                                     error_code="outcome_unknown",
                                     error_message="Upload response lost; check YouTube before retrying.",
                                     retryable=False)
            return AdapterResult(ok=False, error_code="validation_rejected",
                                 error_message=_short(put), retryable=False)
        body = put.json() if put.content else {}
        vid = body.get("id")
        return AdapterResult(
            ok=True, step="inserted", external_ref=vid, external_id=vid,
            external_url=f"https://youtube.com/shorts/{vid}" if vid else None,
        )

    def status(self, *, access_token: str, external_ref: str) -> AdapterResult:
        if external_ref.startswith("http"):
            return AdapterResult(ok=False, error_code="outcome_unknown",
                                 error_message="Upload session cannot be status-checked; check YouTube Studio.",
                                 retryable=False)
        r = self.http.get(f"{API}/videos", params={"part": "status,snippet", "id": external_ref},
                          headers={"Authorization": f"Bearer {access_token}"})
        if r.status_code >= 400:
            return AdapterResult(ok=False, error_code="outcome_unknown",
                                 error_message=_short(r), retryable=False)
        items = r.json().get("items") or []
        if not items:
            return AdapterResult(ok=False, error_code="outcome_unknown",
                                 error_message="Video not found on YouTube.", retryable=False)
        return AdapterResult(
            ok=True, step="inserted", external_ref=external_ref, external_id=external_ref,
            external_url=f"https://youtube.com/shorts/{external_ref}",
        )


def _short(r: httpx.Response) -> str:
    try:
        err = r.json().get("error") or {}
        msg = err.get("message") or r.text
    except Exception:
        msg = r.text
    return (msg or f"HTTP {r.status_code}")[:400]
