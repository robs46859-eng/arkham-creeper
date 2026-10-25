import hashlib
import hmac
import json
import re
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path


MAX_BODY = 1024 * 1024


class Rejected(Exception):
    def __init__(self, status, reason):
        self.status = status
        self.reason = reason
        super().__init__(reason)


class LeaseLost(RuntimeError):
    pass


class DeepWater:
    def __init__(self, root, capacity=1000):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.root.chmod(0o700)
        self.path = self.root / "deep-water.sqlite3"
        self.capacity = capacity
        with self.connect() as database:
            database.executescript("""
                CREATE TABLE IF NOT EXISTS jobs (
                    delivery TEXT PRIMARY KEY, event TEXT NOT NULL, digest TEXT NOT NULL,
                    payload BLOB NOT NULL, state TEXT NOT NULL DEFAULT 'pending',
                    attempts INTEGER NOT NULL DEFAULT 0, available REAL NOT NULL,
                    lease_until REAL, lease_token TEXT, sources BLOB, report TEXT, error TEXT,
                    received REAL NOT NULL
                );
            """)
        self.path.chmod(0o600)

    @contextmanager
    def connect(self):
        database = sqlite3.connect(self.path, timeout=10)
        database.row_factory = sqlite3.Row
        try:
            with database:
                yield database
        finally:
            database.close()

    def accept(self, delivery, event, body):
        digest = hashlib.sha256(body).hexdigest()
        now = time.time()
        with self.connect() as database:
            database.execute("BEGIN IMMEDIATE")
            existing = database.execute("SELECT digest, event FROM jobs WHERE delivery=?", (delivery,)).fetchone()
            if existing:
                if existing["digest"] != digest or existing["event"] != event:
                    raise Rejected(409, "delivery_replay_mismatch")
                return {"delivery": delivery, "duplicate": True, "sha256": digest}
            count = database.execute("SELECT count(*) FROM jobs WHERE state IN ('pending','processing')").fetchone()[0]
            if count >= self.capacity:
                raise Rejected(503, "deep_water_full_retry_later")
            database.execute("INSERT INTO jobs(delivery,event,digest,payload,available,received) VALUES(?,?,?,?,?,?)",
                             (delivery, event, digest, body, now, now))
        return {"delivery": delivery, "duplicate": False, "sha256": digest}

    def claim(self, lease_seconds=300):
        now = time.time()
        token = str(uuid.uuid4())
        with self.connect() as database:
            database.execute("BEGIN IMMEDIATE")
            database.execute("UPDATE jobs SET state='dead',error='worker_lease_exhausted' WHERE state='processing' AND lease_until<? AND attempts>=3", (now,))
            job = database.execute("SELECT * FROM jobs WHERE (state='pending' AND available<=?) OR (state='processing' AND lease_until<? AND attempts<3) ORDER BY received LIMIT 1", (now, now)).fetchone()
            if job is None:
                return None
            database.execute("UPDATE jobs SET state='processing',attempts=attempts+1,lease_until=?,lease_token=? WHERE delivery=?", (now + lease_seconds, token, job["delivery"]))
            return dict(database.execute("SELECT * FROM jobs WHERE delivery=?", (job["delivery"],)).fetchone())

    def finish(self, job, report=None, error=None):
        with self.connect() as database:
            if error:
                state = "dead" if job["attempts"] >= 3 else "pending"
                result = database.execute("UPDATE jobs SET state=?,error=?,available=?,lease_until=NULL WHERE delivery=? AND state='processing' AND lease_token=?",
                                 (state, error, time.time() + 2 ** job["attempts"], job["delivery"], job["lease_token"]))
            else:
                result = database.execute("UPDATE jobs SET state='done',report=?,error=NULL,lease_until=NULL WHERE delivery=? AND state='processing' AND lease_token=?",
                                 (json.dumps(report), job["delivery"], job["lease_token"]))
            return result.rowcount == 1

    def store_sources(self, job, sources):
        with self.connect() as database:
            result = database.execute("UPDATE jobs SET sources=? WHERE delivery=? AND state='processing' AND lease_token=?",
                             (json.dumps(sources).encode(), job["delivery"], job["lease_token"]))
            return result.rowcount == 1

    def records(self):
        with self.connect() as database:
            return [dict(row) for row in database.execute("SELECT delivery,event,digest,state,attempts,report,error FROM jobs ORDER BY received")]


class Sail:
    def __init__(self, water, secret, repositories):
        if not secret or len(secret) < 32:
            raise ValueError("A webhook secret of at least 32 characters is required")
        self.water = water
        self.secret = secret.encode()
        self.repositories = set(repositories)
        if not self.repositories:
            raise ValueError("An explicit repository allowlist is required")

    def capture(self, headers, body):
        if len(body) > MAX_BODY:
            raise Rejected(413, "payload_too_large")
        headers = {key.lower(): value for key, value in headers.items()}
        signature = headers.get("x-hub-signature-256", "")
        expected = "sha256=" + hmac.new(self.secret, body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature.encode(), expected.encode()):
            raise Rejected(401, "invalid_signature")
        delivery = headers.get("x-github-delivery", "")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", delivery):
            raise Rejected(400, "invalid_delivery_id")
        try:
            payload = json.loads(body)
            repository = payload["repository"]["full_name"]
        except (ValueError, TypeError, KeyError, RecursionError):
            raise Rejected(400, "invalid_payload") from None
        if not isinstance(repository, str) or repository not in self.repositories:
            raise Rejected(403, "repository_not_allowed")
        event = headers.get("x-github-event", "")
        if event == "ping":
            return {"status": "afloat", "queued": False}
        if event not in {"push", "pull_request"}:
            return {"status": "ignored", "queued": False}
        return self.water.accept(delivery, event, body)
