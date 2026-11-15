import os
import subprocess
import tempfile
import uuid
from pathlib import Path

import pytest

# Configure the app before anything imports it.
_TMP = Path(tempfile.mkdtemp(prefix="clipapi_test_"))
os.environ.update(
    ENV="dev", DATA_DIR=str(_TMP / "data"),
    DATABASE_URL=os.environ.get("TEST_DATABASE_URL", f"sqlite:///{_TMP / 'test.db'}"),
    SECRET_KEY="test-secret-key-test-secret-key-0000", AUTO_VERIFY_EMAIL="true", FREE_SIGNUP_CREDITS="30",
    STRIPE_WEBHOOK_SECRET="whsec_test", WHISPER_MODEL="none", SIGNUP_LIMIT_PER_IP_PER_HOUR="1000",
    LOGIN_LIMIT_PER_IP_PER_MINUTE="1000", RATE_LIMIT_PER_MINUTE="100000", MIN_DURATION_SEC="5",
)

from fastapi.testclient import TestClient  # noqa: E402

from app.db import init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.pipeline.transcribe import Transcript  # noqa: E402


@pytest.fixture(scope="session")
def client():
    init_db()
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def video() -> Path:
    """40 s synthetic video: quiet tone with a loud burst at 20-24 s, moving test pattern."""
    path = _TMP / "sample.mp4"
    subprocess.run([
        "ffmpeg", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=15:duration=40",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=40",
        "-af", "volume='if(between(t,20,24),1.0,0.02)':eval=frame",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path),
    ], check=True)
    return path


@pytest.fixture
def user(client):
    """A fresh signed-up account: (headers, account_json)."""
    email = f"u{uuid.uuid4().hex[:10]}@example.org"
    r = client.post("/v1/auth/signup", json={"email": email, "password": "correct-horse-9"})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}, r.json()["account"]


class FakeTranscriber:
    """Stands in for Whisper so tests don't download a model."""
    def transcribe(self, wav) -> Transcript:
        return Transcript(words=[(1.0, 1.4, "oh"), (1.4, 1.7, "my"), (1.7, 2.2, "god"), (5.0, 5.5, "no"), (5.5, 6.0, "way")],
                          segments=[(1.0, 2.2, "oh my god"), (5.0, 6.0, "no way")])


@pytest.fixture
def transcriber():
    return FakeTranscriber()
