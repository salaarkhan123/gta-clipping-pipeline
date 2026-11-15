"""Plans and subscriptions, aspect ratios, AI clip metadata, subtitle export."""
import hashlib
import hmac
import json
import time

import httpx
import pytest

from app import worker
from app.ai import ClaudeAI, parse_meta, signal_meta
from app.db import new_session
from app.models import Account
from app.pipeline import PipelineOptions, run_pipeline
from app.pipeline.ff import probe
from app.routes_media import subtitle_cues
from tests.test_api import balance, upload
from tests.test_tools import fetch


def event(kind: str, obj: dict):
    payload = json.dumps({"id": f"evt_{time.time_ns()}", "type": kind, "data": {"object": obj}})
    ts = int(time.time())
    sig = hmac.new(b"whsec_test", f"{ts}.{payload}".encode(), hashlib.sha256).hexdigest()
    return payload, {"stripe-signature": f"t={ts},v1={sig}", "content-type": "application/json"}


def send(client, kind, obj):
    payload, headers = event(kind, obj)
    r = client.post("/webhooks/stripe", content=payload, headers=headers)
    assert r.status_code == 200, r.text


def me(client, headers):
    return client.get("/v1/me", headers=headers).json()


def test_plans_listed_and_checkout_needs_stripe(client, user):
    headers, _ = user
    plans = client.get("/v1/billing/plans").json()
    assert [p["id"] for p in plans["plans"]] == ["free", "starter", "pro", "scale"] and plans["billing_enabled"] is False
    assert me(client, headers)["plan"] == "free"
    for path, body in (("/v1/billing/subscribe", {"plan_id": "pro"}), ("/v1/billing/portal", None)):
        r = client.post(path, json=body, headers=headers)
        assert r.status_code == 503 and r.json()["error"]["code"] == "billing_unavailable"


def test_subscription_lifecycle(client, user):
    headers, account = user
    aid, meta = account["id"], {"account_id": account["id"], "plan_id": "pro", "interval": "month"}
    # invoice.paid can arrive before checkout.session.completed: it alone must be enough.
    inv = {"id": f"in_1_{aid}", "customer": f"cus_{aid}", "subscription_details": {"metadata": meta}}
    send(client, "invoice.paid", inv)
    send(client, "invoice.paid", inv)                                        # redelivery
    assert balance(client, headers) == 30 + 1200 and me(client, headers)["plan"] == "pro"
    send(client, "checkout.session.completed", {"id": f"cs_{aid}", "mode": "subscription", "customer": f"cus_{aid}",
                                                "subscription": f"sub_{aid}", "metadata": meta})
    assert balance(client, headers) == 1230                                  # checkout itself grants nothing
    # Renewal: newer API shape, metadata under parent; plus a forged credits number that must be ignored.
    send(client, "invoice.paid", {"id": f"in_2_{aid}", "customer": f"cus_{aid}", "credits": 999999,
                                  "parent": {"subscription_details": {"metadata": meta}}})
    assert balance(client, headers) == 2430
    # Renewal with no metadata at all: matched by customer id, plan taken from the account.
    send(client, "invoice.paid", {"id": f"in_3_{aid}", "customer": f"cus_{aid}"})
    assert balance(client, headers) == 3630
    r = client.post("/v1/billing/subscribe", json={"plan_id": "starter"}, headers=headers)
    assert r.status_code == 503                                               # (Stripe off in tests)
    send(client, "customer.subscription.deleted", {"id": "sub_someone_else", "customer": f"cus_{aid}"})
    assert me(client, headers)["plan"] == "pro"                               # a different subscription: ignored
    send(client, "customer.subscription.deleted", {"id": f"sub_{aid}", "customer": f"cus_{aid}"})
    assert me(client, headers)["plan"] == "free" and balance(client, headers) == 3630   # credits are kept


def test_yearly_plan_grants_twelve_months_and_bad_events_do_nothing(client, user):
    headers, account = user
    meta = {"account_id": account["id"], "plan_id": "starter", "interval": "year"}
    send(client, "invoice.paid", {"id": f"in_y_{account['id']}", "customer": "cus_y", "lines": {"data": [{"metadata": meta}]}})
    assert balance(client, headers) == 30 + 500 * 12
    send(client, "invoice.paid", {"id": "in_unknown", "customer": "cus_nobody"})
    send(client, "invoice.paid", {"id": "in_badplan", "customer": "cus_y2",
                                  "subscription_details": {"metadata": {"account_id": account["id"], "plan_id": "nope"}}})
    assert balance(client, headers) == 6030 and me(client, headers)["plan"] == "starter"
    payload, headers2 = event("invoice.paid", {"id": "in_forged", "subscription_details": {"metadata": meta}})
    headers2["stripe-signature"] = headers2["stripe-signature"][:-4] + "0000"
    assert client.post("/webhooks/stripe", content=payload, headers=headers2).status_code == 400


def test_paid_plan_exports_1080_and_plan_caps_render_minutes(client, user, video, transcriber, tmp_path):
    headers, account = user
    up = upload(client, headers, video)
    with new_session() as db:
        db.get(Account, account["id"]).plan = "starter"
        db.commit()
    body = {"upload_id": up["upload_id"], "segments": [{"start": 5, "end": 12}], "options": {"aspect": "4:5"}}
    r = client.post("/v1/reframe", json=body, headers=headers)
    assert worker.run_once(transcriber) == "SUCCEEDED"
    clip = client.get(f"/v1/jobs/{r.json()['job_id']}", headers=headers).json()["clips"][0]
    info = probe(fetch(client, clip["video_url"], tmp_path / "a.mp4"))
    assert (info.width, info.height) == (1080, 1350)
    from app.models import Upload
    with new_session() as db:                       # pretend it is a 45-minute video on the Free plan (10 min cap)
        db.get(Account, account["id"]).plan = "free"
        db.get(Upload, up["upload_id"]).duration_sec = 2700
        db.commit()
    r = client.post("/v1/reframe", json={"upload_id": up["upload_id"]}, headers=headers)
    assert r.status_code == 413 and "Free plan" in r.json()["error"]["message"]


@pytest.mark.parametrize("aspect,size", [("9:16", (1080, 1920)), ("1:1", (1080, 1080)), ("4:5", (1080, 1350)),
                                         ("16:9", (1920, 1080))])
def test_aspect_ratios(video, transcriber, tmp_path, aspect, size):
    r = run_pipeline(video, PipelineOptions(max_clips=1, clip_length=10, aspect=aspect, facecam_region="bottom-right"),
                     tmp_path / "o", None, transcriber)[0]
    info = probe(r.video_path)
    assert (info.width, info.height) == size and r.captions_path is not None


def test_resolution_cap_keeps_aspect(video, tmp_path):
    r = run_pipeline(video, PipelineOptions(max_clips=1, clip_length=10, aspect="1:1", max_side=720, facecam_region=None),
                     tmp_path / "o")[0]
    info = probe(r.video_path)
    assert (info.width, info.height) == (720, 720)


def test_parse_meta_sanitises_model_output():
    good = parse_meta('Sure! {"title": "\\"He did NOT see that coming\\"", "description": "d", "hashtags": ["#gta6", "no way!", 7],'
                      ' "virality": {"hook": 150, "flow": "80", "value": -5, "trend": null}, "reason": "r"} thanks')
    assert good["title"] == "He did NOT see that coming" and good["hashtags"] == ["gta6", "noway", "7"]
    assert good["virality"] == {"score": 58, "hook": 100, "flow": 80, "value": 0, "trend": 50} and good["source"] == "ai"
    assert parse_meta("no json here") is None and parse_meta('{"title": ""}') is None and parse_meta("[1,2]") is None
    assert signal_meta(1.4)["virality"]["score"] == 99 and signal_meta(0.0)["virality"]["score"] == 50


def test_claude_client_request_shape_and_failure_is_swallowed(tmp_path):
    seen = {}

    def handler(request: httpx.Request):
        seen["headers"], seen["body"] = request.headers, json.loads(request.content)
        return httpx.Response(200, json={"content": [{"type": "text", "text": json.dumps({
            "title": "Clean getaway", "description": "x", "hashtags": ["gta"],
            "virality": {"hook": 70, "flow": 60, "value": 80, "trend": 50}, "reason": "y"})}]})
    thumb = tmp_path / "t.jpg"
    thumb.write_bytes(b"\xff\xd8fake")
    ai = ClaudeAI("sk-test", "model-x", httpx.Client(transport=httpx.MockTransport(handler)))
    meta = ai.clip_meta("no way bro", {"length": 30, "signals": {"audio": 1.0}}, thumb)
    assert meta["title"] == "Clean getaway" and meta["virality"]["score"] == 65
    assert seen["headers"]["x-api-key"] == "sk-test" and seen["headers"]["anthropic-version"] == "2023-06-01"
    assert seen["body"]["model"] == "model-x" and [b["type"] for b in seen["body"]["messages"][0]["content"]] == ["image", "text"]
    assert "no way bro" in seen["body"]["messages"][0]["content"][1]["text"]
    down = ClaudeAI("k", "m", httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(529))))
    assert down.clip_meta("x", {}) is None


class FakeAI:
    def __init__(self):
        self.calls = []

    def clip_meta(self, transcript, context, thumb=None):
        self.calls.append((transcript, context, thumb))
        if len(self.calls) == 2:
            return None                                # the API failed for this clip
        return {"title": "Big moment", "description": "d", "hashtags": ["gta6"],
                "virality": {"score": 81, "hook": 90, "flow": 70, "value": 85, "trend": 79}, "reason": "r", "source": "ai"}


def test_clips_get_ai_titles_scores_and_subtitles(client, user, video, transcriber):
    headers, _ = user
    up = upload(client, headers, video)
    r = client.post("/v1/clips", json={"upload_id": up["upload_id"], "options": {"max_clips": 1, "clip_length": 10}},
                    headers=headers)
    ai = FakeAI()
    assert worker.run_once(transcriber, ai=ai) == "SUCCEEDED"
    clip = client.get(f"/v1/jobs/{r.json()['job_id']}", headers=headers).json()["clips"][0]
    assert clip["title"] == "Big moment" and clip["virality"]["score"] == 81 and clip["hashtags"] == ["gta6"]
    assert ai.calls[0][0] and ai.calls[0][2] is not None                    # got the clip's words and a frame
    srt = client.get(f"/v1/clips/{clip['id']}/subtitles", headers=headers)
    assert srt.status_code == 200 and srt.text.startswith("1\n00:00:0") and " --> " in srt.text
    vtt = client.get(f"/v1/clips/{clip['id']}/subtitles?format=vtt", headers=headers).text
    assert vtt.startswith("WEBVTT") and "," not in vtt.split("\n")[2]
    assert client.get(f"/v1/clips/{clip['id']}/subtitles?format=txt", headers=headers).text.strip()
    assert client.get(f"/v1/clips/{clip['id']}/subtitles?format=doc", headers=headers).status_code == 422
    # Second job: the AI call fails -> the clip still succeeds, with no title or score. No AI at all -> same.
    for kw in ({"ai": ai}, {}):
        r = client.post("/v1/clips", json={"upload_id": up["upload_id"], "options": {"max_clips": 1, "clip_length": 10,
                                                                                    "captions": False}}, headers=headers)
        assert worker.run_once(transcriber, **kw) == "SUCCEEDED"
        clip = client.get(f"/v1/jobs/{r.json()['job_id']}", headers=headers).json()["clips"][0]
        assert clip["title"] is None and clip["virality"] is None
        assert client.get(f"/v1/clips/{clip['id']}/subtitles", headers=headers).status_code == 404


def test_subtitle_cues_split_on_gaps_and_length():
    words = [{"start": i * 0.4, "end": i * 0.4 + 0.3, "text": f"w{i}"} for i in range(9)]
    words.append({"start": 10.0, "end": 10.3, "text": "late"})
    cues = subtitle_cues(words)
    assert [c[2].split()[0] for c in cues] == ["w0", "w7", "late"] and cues[0][1] > cues[0][0]
