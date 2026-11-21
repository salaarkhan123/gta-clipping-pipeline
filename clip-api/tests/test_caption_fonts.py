"""An account's own caption fonts (app/routes_fonts.py): checked on upload, kept per account under its uploads
prefix, used by caption_look "custom:<id>", and a job whose font is gone fails and is refunded."""
from app import routes_fonts, worker
from app.pipeline.fonts import FONT_DIR, MAX_FONT_BYTES
from app.storage import get_storage
from tests.test_api import balance, upload

FONT = (FONT_DIR / "Bangers-Regular.ttf").read_bytes()


def send(client, headers, data=FONT, name="My Font.ttf", confirmed=True):
    return client.post(f"/v1/fonts?filename={name}&licence_confirmed={'true' if confirmed else 'false'}",
                       content=data, headers=headers)


def test_upload_list_use_and_delete(client, user):
    headers, account = user
    assert client.get("/v1/fonts", headers=headers).json()["fonts"] == []
    r = send(client, headers)
    assert r.status_code == 201, r.text
    font = r.json()
    assert font["family"] == "Bangers" and font["font"] == f"custom:{font['id']}" and "licence" in font
    assert font["bytes"] == len(FONT) and font["filename"] == "My Font.ttf"
    listed = client.get("/v1/fonts", headers=headers).json()
    assert [f["id"] for f in listed["fonts"]] == [font["id"]] and "responsible" in listed["licence"]
    key = routes_fonts.font_key(account["id"], font["id"])
    assert key.startswith(f"uploads/{account['id']}/") and get_storage().exists(key)    # deleted with the account
    assert client.delete(f"/v1/fonts/{font['id']}", headers=headers).json() == {"deleted": font["id"]}
    assert not get_storage().exists(key) and client.get("/v1/fonts", headers=headers).json()["fonts"] == []
    assert client.delete(f"/v1/fonts/{font['id']}", headers=headers).status_code == 404


def test_only_licensed_real_fonts_within_the_limits(client, user):
    headers, _ = user
    assert send(client, headers, confirmed=False).json()["error"]["code"] == "licence_not_confirmed"
    assert send(client, headers, name="x.woff").status_code == 415
    r = send(client, headers, data=b"MZ not a font at all")
    assert r.status_code == 422 and r.json()["error"]["code"] == "bad_font"
    assert send(client, headers, data=FONT[:300]).json()["error"]["code"] == "bad_font"
    assert send(client, headers, data=b"\0" * (MAX_FONT_BYTES + 1)).status_code == 413
    for _ in range(routes_fonts.MAX_FONTS):
        assert send(client, headers).status_code == 201
    assert send(client, headers).json()["error"]["code"] == "too_many_fonts"


def test_another_accounts_fonts_are_invisible_and_untouchable(client, user):
    headers, _ = user
    font = send(client, headers).json()
    r = client.post("/v1/auth/signup", json={"email": "other-font@example.org", "password": "correct-horse-9"})
    other = {"Authorization": f"Bearer {r.json()['token']}"}
    assert client.get("/v1/fonts", headers=other).json()["fonts"] == []
    assert client.delete(f"/v1/fonts/{font['id']}", headers=other).status_code == 404
    assert client.get("/v1/fonts").status_code == 401


def test_the_worker_hands_the_font_to_the_renderer(client, user, tmp_path):
    headers, account = user
    font = send(client, headers).json()
    options = {"caption_look": {"font": font["font"]}}
    worker._fetch_caption_font(get_storage(), account["id"], options, tmp_path)
    assert options["caption_font_file"].endswith(".ttf") and (tmp_path / "caption_font.ttf").read_bytes() == FONT
    plain = {"caption_look": {"font": "poppins"}}
    worker._fetch_caption_font(get_storage(), account["id"], plain, tmp_path)
    assert "caption_font_file" not in plain


def test_a_job_whose_font_was_deleted_fails_and_is_refunded(client, user, video, transcriber):
    headers, _ = user
    font = send(client, headers).json()
    up = upload(client, headers, video)
    r = client.post("/v1/clips", json={"upload_id": up["upload_id"], "options": {"caption_look": {"font": font["font"]}}},
                    headers=headers)
    assert r.status_code == 202, r.text
    before = balance(client, headers)
    client.delete(f"/v1/fonts/{font['id']}", headers=headers)
    assert worker.run_once(transcriber) == "FAILED"
    job = client.get(f"/v1/jobs/{r.json()['job_id']}", headers=headers).json()
    assert job["error"]["code"] == "caption_font_missing" and job["credits_charged"] == 0
    assert balance(client, headers) > before
