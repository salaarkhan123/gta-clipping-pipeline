#!/usr/bin/env python3
"""Admin tool. Run inside the api container:  docker compose exec api python scripts/admin.py <command>

  create-account EMAIL PASSWORD [--credits N]   create a verified account (invite-only use)
  mint-key EMAIL [--name NAME]                  create an API key and print it once
  grant EMAIL CREDITS [--note TEXT]             add (or with a negative number, remove) credits
  balance EMAIL                                 show balance and recent ledger rows
  suspend EMAIL / unsuspend EMAIL               block or unblock an account
  stuck                                         list QUEUED/RUNNING jobs
  send-test-email --to ADDRESS                  send one email through the configured SMTP (exit 2: not configured, 1: failed)
  selftest                                      load every model and tool once (run in the worker container)
"""
import argparse
import secrets
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app import ledger  # noqa: E402
from app.db import init_db, new_session  # noqa: E402
from app.models import Account, ApiKey, CreditLedger, Job, new_id  # noqa: E402
from app.security import hash_password, new_api_key  # noqa: E402


def find(db, email: str) -> Account:
    account = db.execute(select(Account).where(Account.email == email.lower())).scalar_one_or_none()
    if not account:
        sys.exit(f"No account with email {email}")
    return account


def selftest() -> int:
    """Exercises everything that could not be tested before deploy: real models on this machine."""
    import subprocess
    import tempfile
    import time
    import numpy as np
    from app.config import get_settings
    s, failed, tmp = get_settings(), 0, Path(tempfile.mkdtemp())

    def check(name, fn):
        nonlocal failed
        t = time.time()
        try:
            print(f"OK    {name}: {fn()}  ({time.time() - t:.1f}s)")
        except Exception as e:
            failed += 1
            print(f"FAIL  {name}: {type(e).__name__}: {str(e)[:300]}")

    def ffmpeg():
        out = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True, check=True).stdout
        assert " ass " in out, "ffmpeg has no libass (captions cannot be burned in)"
        return "libass present"

    def whisper(model, **kw):
        from app.pipeline.transcribe import FasterWhisperTranscriber
        wav = tmp / "t.wav"
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=300:duration=3",
                        "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(wav)], check=True)
        FasterWhisperTranscriber(model, **kw).transcribe(wav)
        return f"{model} loaded and ran"

    def clip():
        from app.pipeline.visual import FastembedClip
        e = FastembedClip()
        img = np.zeros((2, 224, 224, 3), np.uint8)
        img[0, :, :, 0] = 255                                   # one red image, one black
        iv, tv = e.embed_images(img), e.embed_text(["a solid red image"])
        sims = iv @ tv[0]
        assert iv.shape[1] == tv.shape[1], "image and text embeddings have different sizes"
        assert sims[0] > sims[1], f"red image did not match 'red' better than black ({sims})"
        return f"dim {iv.shape[1]}, red {sims[0]:.3f} > black {sims[1]:.3f}"

    def faces():
        from app.pipeline.facecam import _detector
        _detector()
        return "face detector loaded"

    def storage():
        from app.storage import get_storage
        st, f = get_storage(), tmp / "x.txt"
        f.write_text("ok")
        st.put("selftest/x.txt", f)
        assert st.exists("selftest/x.txt")
        st.delete("selftest/x.txt")
        return f"{s.storage_backend} read/write"

    check("ffmpeg", ffmpeg)
    if s.whisper_model.lower() != "none":
        check("captions model", lambda: whisper(s.whisper_model))
    if s.whisper_index_model.lower() != "none":
        check("search index model", lambda: whisper(s.whisper_index_model, beam_size=1, words=False))
    if s.visual_search:
        check("visual search (CLIP)", clip)
    check("facecam detection", faces)
    check("storage", storage)
    print("ALL OK" if not failed else f"{failed} CHECK(S) FAILED")
    return 1 if failed else 0


def send_test_email(to: str) -> int:
    """Sends one message through app/emailer.py. Never prints the SMTP password."""
    from app.config import get_settings
    from app.emailer import deliver, missing_smtp_keys
    missing = missing_smtp_keys()
    if missing:
        print(f"SMTP is not configured. Missing: {', '.join(missing)}", file=sys.stderr)
        return 2
    s = get_settings()
    try:
        deliver(to, "Clip API test email", "If you can read this, SMTP delivery works.")
    except Exception as e:
        detail = f"{type(e).__name__}: {e}"
        if s.smtp_password:
            detail = detail.replace(s.smtp_password, "***")
        print(f"Send failed via {s.smtp_host}:{s.smtp_port}: {detail}", file=sys.stderr)
        return 1
    print(f"Sent one message to {to} from {s.email_from} via {s.smtp_host}:{s.smtp_port}. Check the inbox.")
    return 0


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create-account"); c.add_argument("email"); c.add_argument("password"); c.add_argument("--credits", type=int, default=0)
    c = sub.add_parser("mint-key"); c.add_argument("email"); c.add_argument("--name", default="admin-issued")
    c = sub.add_parser("grant"); c.add_argument("email"); c.add_argument("credits", type=int); c.add_argument("--note", default="Admin adjustment")
    c = sub.add_parser("balance"); c.add_argument("email")
    c = sub.add_parser("suspend"); c.add_argument("email")
    c = sub.add_parser("unsuspend"); c.add_argument("email")
    sub.add_parser("stuck")
    sub.add_parser("selftest")
    c = sub.add_parser("send-test-email"); c.add_argument("--to", required=True)
    args = p.parse_args()

    if args.cmd == "selftest":
        sys.exit(selftest())
    if args.cmd == "send-test-email":
        sys.exit(send_test_email(args.to))
    init_db()
    with new_session() as db:
        if args.cmd == "create-account":
            if len(args.password) < 8:
                sys.exit("Password must be at least 8 characters.")
            account = Account(id=new_id("acct"), email=args.email.lower(), password_hash=hash_password(args.password),
                              email_verified=True, webhook_secret=secrets.token_urlsafe(32))
            db.add(account)
            db.flush()
            if args.credits > 0:
                ledger.grant(db, account.id, args.credits, "grant", f"admin:{uuid.uuid4().hex}", "Admin grant")
            db.commit()
            print(f"Created {account.email} ({account.id}) with {ledger.balance(db, account.id)} credits")
        elif args.cmd == "mint-key":
            account = find(db, args.email)
            raw, prefix, digest = new_api_key()
            db.add(ApiKey(id=new_id("key"), account_id=account.id, name=args.name, prefix=prefix, key_hash=digest))
            db.commit()
            print(f"API key for {account.email} (shown once):\n{raw}")
        elif args.cmd == "grant":
            account = find(db, args.email)
            ledger.grant(db, account.id, args.credits, "adjust", f"admin:{uuid.uuid4().hex}", args.note)
            db.commit()
            print(f"{account.email}: balance is now {ledger.balance(db, account.id)}")
        elif args.cmd == "balance":
            account = find(db, args.email)
            print(f"{account.email}: {ledger.balance(db, account.id)} credits")
            rows = db.execute(select(CreditLedger).where(CreditLedger.account_id == account.id)
                              .order_by(CreditLedger.id.desc()).limit(15)).scalars()
            for r in rows:
                print(f"  {r.created_at:%Y-%m-%d %H:%M} {r.kind:8} {r.delta:+6d} {r.job_id or ''} {r.note or ''}")
        elif args.cmd in ("suspend", "unsuspend"):
            account = find(db, args.email)
            account.status = "suspended" if args.cmd == "suspend" else "active"
            db.commit()
            print(f"{account.email}: {account.status}")
        elif args.cmd == "stuck":
            jobs = db.execute(select(Job).where(Job.status.in_(("QUEUED", "RUNNING"))).order_by(Job.created_at)).scalars()
            for j in jobs:
                print(f"{j.id} {j.status:8} stage={j.stage} progress={j.progress} created={j.created_at:%m-%d %H:%M} "
                      f"heartbeat={j.heartbeat_at}")


if __name__ == "__main__":
    main()
