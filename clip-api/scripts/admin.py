#!/usr/bin/env python3
"""Admin tool. Run inside the api container:  docker compose exec api python scripts/admin.py <command>

  create-account EMAIL PASSWORD [--credits N]   create a verified account (invite-only use)
  mint-key EMAIL [--name NAME]                  create an API key and print it once
  grant EMAIL CREDITS [--note TEXT]             add (or with a negative number, remove) credits
  balance EMAIL                                 show balance and recent ledger rows
  suspend EMAIL / unsuspend EMAIL               block or unblock an account
  stuck                                         list WAITING/QUEUED/RUNNING jobs
  make-admin EMAIL / revoke-admin EMAIL         let an account use the admin routes (/v1/admin/...) from its login
  ops-status                                    queue and worker health as key=value lines (read-only; ops.sh status)
  send-test-email --to ADDRESS                  send one email through the configured provider, Resend or SMTP
                                                (exit 2: not configured, 1: failed)
  bump-token-epoch                              void every password-reset and email-verification link already sent
  selftest                                      load every model and tool once (run in the worker container)
  db-status                                     schema revision and differences from the models (read-only)
  stripe-check                                  Stripe key mode, key accepted, each plan's Price matches app/plans.py,
                                                webhook secret set (read-only; prints no secret)
  migrate                                       upgrade the schema to the latest revision (deploy.sh runs it)
  takedown --url URL | --account ID_OR_EMAIL [--dry-run]
                                                remove every upload, clip and file imported from a source URL, or all
                                                of one account's link imports; cancels and refunds their jobs
  inspect-upload UPLOAD_ID                      jobs, clips (including soft-deleted), ledger and transcript keys
                                                for one upload (read-only)
  recover-clips JOB_ID [--dry-run]              undelete soft-deleted clips whose video/preview file still exists
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
from app.models import Account, ApiKey, Clip, CreditLedger, Job, Upload, new_id, utcnow  # noqa: E402
from app.security import hash_password, new_api_key  # noqa: E402
from app.storage import get_storage, transcript_key, transcript_parts_key  # noqa: E402
from app.thumbnails import frame_key_of  # noqa: E402


def find(db, email: str) -> Account:
    account = db.execute(select(Account).where(Account.email == email.lower())).scalar_one_or_none()
    if not account:
        sys.exit(f"No account with email {email}")
    return account


def inspect_upload(upload_id: str) -> int:
    """Read-only dump of jobs/clips/ledger/transcript presence for one upload (incident forensics)."""
    storage = get_storage()
    with new_session() as db:
        up = db.get(Upload, upload_id)
        if up is None:
            print(f"upload {upload_id}: not found")
            return 1
        print(f"upload {up.id} account={up.account_id} duration={up.duration_sec}s "
              f"deleted={up.deleted_at} analyzed={up.analyzed} key={up.storage_key}")
        print(f"  transcript_whole={storage.exists(transcript_key(up.id))} "
              f"transcript_parts={storage.exists(transcript_parts_key(up.id))} "
              f"source_exists={storage.exists(up.storage_key)}")
        jobs = db.execute(select(Job).where(Job.upload_id == upload_id).order_by(Job.created_at)).scalars().all()
        for j in jobs:
            print(f"job {j.id} {j.status} stage={j.stage} progress={j.progress} "
                  f"reserved={j.credits_reserved} charged={j.credits_charged} "
                  f"error={j.error_code}:{j.error_message}")
            print(f"  created={j.created_at} started={j.started_at} finished={j.finished_at} "
                  f"heartbeat={j.heartbeat_at}")
            if j.result:
                counts = (j.result or {}).get("counts") or {}
                print(f"  result.partial={j.result.get('partial')} counts={counts} "
                      f"stages={list((j.result.get('stages') or j.result.get('timings') or {}).keys())}")
            for c in db.execute(select(Clip).where(Clip.job_id == j.id).order_by(Clip.idx)).scalars():
                media = c.video_key or c.preview_key
                print(f"  clip {c.id} idx={c.idx} deleted={c.deleted_at} "
                      f"media={media} media_exists={storage.exists(media) if media else False} "
                      f"thumb_exists={storage.exists(c.thumb_key) if c.thumb_key else False}")
            for r in db.execute(select(CreditLedger).where(CreditLedger.job_id == j.id)
                                .order_by(CreditLedger.id)).scalars():
                print(f"  ledger {r.kind} {r.delta:+d} key={r.idempotency_key} note={r.note}")
    return 0


def recover_clips(job_id: str, dry_run: bool = False) -> int:
    """Undelete soft-deleted clips whose primary media object is still in storage."""
    storage = get_storage()
    with new_session() as db:
        job = db.get(Job, job_id)
        if job is None:
            print(f"job {job_id}: not found")
            return 1
        restored, missing = 0, 0
        for c in db.execute(select(Clip).where(Clip.job_id == job_id).order_by(Clip.idx)).scalars():
            media = c.video_key or c.preview_key
            if c.deleted_at is None:
                print(f"  keep {c.id} (already live)")
                continue
            if not media or not storage.exists(media):
                missing += 1
                print(f"  skip {c.id} (deleted, media missing: {media})")
                continue
            print(f"  restore {c.id} media={media}")
            if not dry_run:
                c.deleted_at = None
            restored += 1
        if not dry_run and restored:
            db.commit()
        print(f"{'would restore' if dry_run else 'restored'}={restored} missing_media={missing} job={job_id} "
              f"status={job.status}")
    return 0 if restored or missing == 0 else 1


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


def stripe_check() -> int:
    """Read-only check of the Stripe settings after a deploy or a key rotation. Prints no secret. Exit 2: no key."""
    import stripe
    from app.config import get_settings
    from app.deps import ApiError
    from app.plans import PLANS, stripe_price_id
    from app.routes_billing import _check_price
    s, failed = get_settings(), 0
    print(f"stripe library {stripe.VERSION}, API version {stripe.api_version}")
    key = s.stripe_secret_key
    if not key:
        print("FAIL  STRIPE_SECRET_KEY is not set")
        return 2
    print(f"key mode: {'live' if '_live_' in key else 'test' if '_test_' in key else 'unknown'}")
    try:
        print(f"OK    key accepted (account {stripe.Account.retrieve(api_key=key).id})")
    except Exception as e:
        failed += 1
        print(f"FAIL  key refused: {type(e).__name__}")
    for plan in PLANS:
        for interval in ("month", "year"):
            cents = plan.get(f"price_{interval}_cents") or 0
            if cents <= 0:
                continue
            name, price_id = f"{plan['id']}/{interval}", stripe_price_id(plan, interval)
            if not price_id:
                failed += 1
                print(f"FAIL  {name}: no Price ID configured")
                continue
            try:
                _check_price(stripe.Price.retrieve(price_id, api_key=key, expand=["product"]), plan, interval, s.currency)
                print(f"OK    {name}: {price_id}")
            except ApiError:
                failed += 1
                print(f"FAIL  {name}: {price_id} does not match app/plans.py (the log line above says how)")
            except Exception as e:
                failed += 1
                print(f"FAIL  {name}: {price_id}: {type(e).__name__}")
    print("OK    STRIPE_WEBHOOK_SECRET is set" if s.stripe_webhook_secret else "FAIL  STRIPE_WEBHOOK_SECRET is not set")
    failed += 0 if s.stripe_webhook_secret else 1
    print("ALL OK" if not failed else f"{failed} CHECK(S) FAILED")
    return 1 if failed else 0


def send_test_email(to: str) -> int:
    """Sends one message through app/emailer.py (Resend or SMTP). Never prints a password or an API key."""
    from app.config import get_settings
    from app.emailer import deliver, mask, missing_keys, provider
    missing = missing_keys()
    if missing:
        print(f"Email is not configured. Missing: {', '.join(missing)}", file=sys.stderr)
        return 2
    s, via = get_settings(), provider()
    where = "Resend API" if via == "resend" else f"{s.smtp_host}:{s.smtp_port}"
    try:
        msg_id = deliver(to, "ClutchClips test email", "If you can read this, email delivery works.",
                         idempotency_key=f"test:{uuid.uuid4().hex}")
    except Exception as e:
        detail = f"{type(e).__name__}: {e}"
        for secret in (s.smtp_password, s.resend_api_key):
            if secret:
                detail = detail.replace(secret, "***")
        print(f"Send failed via {where}: {detail}", file=sys.stderr)
        return 1
    print(f"Sent one message to {to} from {s.email_from} via {where}"
          + (f" (id {msg_id})" if msg_id else "") + ". Check the inbox.")
    return 0


def db_status() -> int:
    """Read-only: revision now, latest revision, and what differs from app/models.py. Exit 1 if not at head."""
    from alembic.autogenerate import compare_metadata
    from alembic.runtime.migration import MigrationContext
    from sqlalchemy import inspect

    from app.db import Base, get_engine
    from app.migrate import current, head
    engine = get_engine()
    now, latest = current(engine), head()
    with engine.connect() as conn:
        legacy = now is None and "accounts" in inspect(conn).get_table_names()
        diffs = compare_metadata(MigrationContext.configure(conn, opts={"compare_type": True}), Base.metadata)
    print(f"revision {now or ('none (from before migrations)' if legacy else 'none (empty database)')} · latest {latest}")
    for d in diffs:
        print(f"  differs: {d}")
    if legacy:
        print("migrate will bring it to the baseline (add missing columns and indexes), then stamp it")
    return 0 if now == latest else 1


def ops_status() -> int:
    """Read-only queue and config health for monitoring. Ages in whole minutes; -1 when there is nothing to measure.
    Config lines are 1/0 for "is it set": names only, never a value."""
    from sqlalchemy import func

    from app.config import get_settings
    from app.emailer import missing_smtp_keys

    def minutes(t) -> int:
        return -1 if t is None else int((utcnow() - t).total_seconds() // 60)

    with new_session() as db:
        counts = dict(db.execute(select(Job.status, func.count()).where(Job.status.in_(("QUEUED", "RUNNING")))
                                 .group_by(Job.status)).all())
        oldest = db.execute(select(func.min(Job.created_at)).where(Job.status == "QUEUED")).scalar_one()
        stalest = db.execute(select(func.min(Job.heartbeat_at)).where(Job.status == "RUNNING")).scalar_one()
        last = db.execute(select(func.max(Job.started_at))).scalar_one()
    print(f"jobs_running={counts.get('RUNNING', 0)}")
    print(f"jobs_queued={counts.get('QUEUED', 0)}")
    print(f"oldest_queued_min={minutes(oldest)}")
    print(f"stalest_heartbeat_min={minutes(stalest)}")
    print(f"last_claim_min={minutes(last)}")
    s = get_settings()
    print(f"email_configured={int(not missing_smtp_keys())}")
    print(f"stripe_configured={int(bool(s.stripe_secret_key))}")
    print(f"stripe_webhook_configured={int(bool(s.stripe_webhook_secret))}")
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
    c = sub.add_parser("make-admin"); c.add_argument("email")
    c = sub.add_parser("revoke-admin"); c.add_argument("email")
    sub.add_parser("stuck")
    sub.add_parser("ops-status")
    sub.add_parser("selftest")
    sub.add_parser("db-status")
    sub.add_parser("stripe-check")
    sub.add_parser("migrate")
    c = sub.add_parser("send-test-email"); c.add_argument("--to", required=True)
    sub.add_parser("bump-token-epoch")
    c = sub.add_parser("takedown")
    target = c.add_mutually_exclusive_group(required=True)
    target.add_argument("--url"); target.add_argument("--account")
    c.add_argument("--dry-run", action="store_true")
    c = sub.add_parser("inspect-upload"); c.add_argument("upload_id")
    c = sub.add_parser("recover-clips"); c.add_argument("job_id"); c.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    if args.cmd == "selftest":
        sys.exit(selftest())
    if args.cmd == "send-test-email":
        sys.exit(send_test_email(args.to))
    if args.cmd == "bump-token-epoch":
        from app import token_epoch
        print(f"token epoch is now {token_epoch.bump()}: every reset and verification link sent before is void")
        sys.exit(0)
    if args.cmd == "stripe-check":
        sys.exit(stripe_check())
    if args.cmd == "db-status":
        sys.exit(db_status())
    if args.cmd == "ops-status":
        sys.exit(ops_status())
    if args.cmd == "migrate":
        from app.db import get_engine
        from app.migrate import migrate
        before, after = migrate(get_engine())
        print(f"schema {before or 'empty'} -> {after}" if before != after else f"schema already at {after}")
        sys.exit(0)
    init_db()
    if args.cmd == "takedown":
        from app.ingest.takedown import takedown
        try:
            report = takedown(url=args.url, account=args.account, dry_run=args.dry_run)
        except LookupError as e:
            sys.exit(str(e))
        print("\n".join(report.lines()))
        sys.exit(0)
    if args.cmd == "inspect-upload":
        sys.exit(inspect_upload(args.upload_id))
    if args.cmd == "recover-clips":
        sys.exit(recover_clips(args.job_id, dry_run=args.dry_run))
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
        elif args.cmd in ("make-admin", "revoke-admin"):
            account = find(db, args.email)
            account.is_admin = args.cmd == "make-admin"
            db.commit()
            print(f"{account.email}: {'admin' if account.is_admin else 'not an admin'}")
        elif args.cmd == "stuck":
            jobs = db.execute(select(Job).where(Job.status.in_(("WAITING", "QUEUED", "RUNNING"))).order_by(Job.created_at)).scalars()
            for j in jobs:
                print(f"{j.id} {j.status:8} stage={j.stage} progress={j.progress} created={j.created_at:%m-%d %H:%M} "
                      f"heartbeat={j.heartbeat_at}")


if __name__ == "__main__":
    main()
