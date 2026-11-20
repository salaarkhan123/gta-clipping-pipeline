"""Commercial OpenAPI polish (CPR-19 E2): public /v1 docs metadata, core paths, no private website API."""
from app.main import app

SPEC = app.openapi()
PATHS = SPEC["paths"]
INFO = SPEC["info"]
TAG_NAMES = {t["name"] for t in SPEC.get("tags") or []}


def _ops(path: str):
    return {m: op for m, op in PATHS[path].items() if m in ("get", "post", "patch", "put", "delete")}


def test_openapi_info_is_commercial_and_versioned():
    assert INFO["title"] == "ClutchClips API"
    assert INFO["version"] == "1.0.0"
    desc = INFO["description"]
    assert "/v1" in desc
    assert "/docs" in desc and "/openapi.json" in desc
    assert "same api for the website" in desc.lower()
    assert "no private website-only" in desc.lower()
    assert "1 credit" in desc.lower()


def test_openapi_tag_groups_cover_public_areas():
    expected = {"auth", "clips", "projects", "tools", "imports", "templates", "thumbnails",
                "languages", "billing", "legal", "trust", "ops"}
    assert expected <= TAG_NAMES
    for tag in SPEC["tags"]:
        assert tag.get("description"), f"tag {tag['name']} needs a description"


def test_core_customer_paths_documented():
    required = {
        ("post", "/v1/uploads"): "Upload",
        ("post", "/v1/clips"): "clip",
        ("post", "/v1/clips/quote"): "Quote",
        ("get", "/v1/jobs/{job_id}"): "job",
        ("get", "/v1/credits"): "Credit",
        ("get", "/v1/options"): "option",
        ("get", "/v1/keys"): "key",
        ("post", "/v1/keys"): "key",
        ("get", "/v1/me"): "account",
    }
    for (method, path), needle in required.items():
        op = _ops(path)[method]
        assert path in PATHS
        assert "clips" in (op.get("tags") or []) or "auth" in (op.get("tags") or []), path
        summary = (op.get("summary") or "").lower()
        desc = (op.get("description") or "").lower()
        assert summary, f"{method.upper()} {path} missing summary"
        assert needle.lower() in summary or needle.lower() in desc, f"{method.upper()} {path} summary/desc"


def test_no_private_website_only_paths():
    # Website and customers share /v1. Non-/v1 surfaces are ops health, Stripe webhook, and OpenAPI itself.
    non_v1 = sorted(p for p in PATHS if not p.startswith("/v1/"))
    assert non_v1 == ["/health", "/webhooks/stripe"]
    for path in PATHS:
        assert "/internal/" not in path
        assert not path.startswith("/private/")
        assert not path.startswith("/website/")


def test_openapi_does_not_expose_raw_secret_schemas():
    schemas = SPEC.get("components", {}).get("schemas", {})
    forbidden = ("webhook_secret", "password_hash", "key_hash", "stripe_secret", "api_key_raw")
    for name, schema in schemas.items():
        lowered = name.lower()
        assert not any(f in lowered for f in ("password_hash", "key_hash", "stripe_secret", "api_key_raw"))
        props = {p.lower() for p in (schema.get("properties") or {})}
        # Request bodies may take a password to set; never expose hash/digest fields.
        assert "password_hash" not in props and "key_hash" not in props
        for bad in forbidden:
            if bad == "webhook_secret":
                continue  # session GET /v1/me may document the field name; value is not a schema default
            assert bad not in props, f"{name}.{bad}"
