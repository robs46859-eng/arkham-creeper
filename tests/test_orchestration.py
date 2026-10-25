import base64
import hashlib
import hmac
import json
import tempfile
import threading
import unittest
from pathlib import Path

from creeper.digest import SpatialModel, digest_once
from creeper.ingress import DeepWater, MAX_BODY, Rejected, Sail
from creeper.source import GitHubSources, safe_path


SECRET = "test-only-webhook-secret-32-characters"
REPOSITORY = "example/synthetic-clinic"


def signed(body, delivery="delivery-1", event="push"):
    return {"X-GitHub-Delivery": delivery, "X-GitHub-Event": event,
            "X-Hub-Signature-256": "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()}


class OrchestrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = SpatialModel()

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.water = DeepWater(self.temporary.name)
        self.sail = Sail(self.water, SECRET, [REPOSITORY])
        self.body = json.dumps({"repository": {"full_name": REPOSITORY}, "before": "a" * 40, "after": "b" * 40}).encode()

    def test_signature_before_json(self):
        with self.assertRaises(Rejected) as raised:
            self.sail.capture({}, b"not json")
        self.assertEqual(raised.exception.status, 401)
        self.assertEqual(self.water.records(), [])

    def test_reject_wrong_repository_and_large_payload(self):
        body = json.dumps({"repository": {"full_name": "someone/else"}}).encode()
        with self.assertRaises(Rejected) as raised:
            self.sail.capture(signed(body), body)
        self.assertEqual(raised.exception.status, 403)
        with self.assertRaises(Rejected) as raised:
            self.sail.capture({}, b"a" * (MAX_BODY + 1))
        self.assertEqual(raised.exception.status, 413)

    def test_durable_idempotency_and_replay_mismatch(self):
        first = self.sail.capture(signed(self.body), self.body)
        restarted = Sail(DeepWater(self.temporary.name), SECRET, [REPOSITORY])
        self.assertTrue(restarted.capture(signed(self.body), self.body)["duplicate"])
        self.assertFalse(first["duplicate"])
        changed = self.body + b" "
        with self.assertRaises(Rejected) as raised:
            restarted.capture(signed(changed), changed)
        self.assertEqual(raised.exception.status, 409)
        with self.assertRaises(Rejected):
            restarted.capture(signed(self.body, event="pull_request"), self.body)
        self.assertEqual(len(self.water.records()), 1)

    def test_queue_backpressure(self):
        self.water.capacity = 1
        self.sail.capture(signed(self.body), self.body)
        with self.assertRaises(Rejected) as raised:
            self.sail.capture(signed(self.body, "delivery-2"), self.body)
        self.assertEqual(raised.exception.status, 503)

    def test_concurrent_claim_and_expired_lease_fencing(self):
        self.sail.capture(signed(self.body), self.body)
        claims = []
        threads = [threading.Thread(target=lambda: claims.append(self.water.claim())) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(sum(job is not None for job in claims), 1)
        old = next(job for job in claims if job)
        with self.water.connect() as database:
            database.execute("UPDATE jobs SET lease_until=0")
        new = self.water.claim()
        self.water.finish(old, report={"stale": True})
        self.assertEqual(self.water.records()[0]["state"], "processing")
        self.water.finish(new, report={"current": True})
        self.assertEqual(json.loads(self.water.records()[0]["report"]), {"current": True})

    def test_failures_retry_then_dead_letter(self):
        self.sail.capture(signed(self.body), self.body)
        def unavailable(*_arguments):
            raise ConnectionError("sensitive detail must not leak")
        for _attempt in range(3):
            result = digest_once(self.water, unavailable, self.model)
            self.assertEqual(result["disposition"], "analysis_unavailable")
            with self.water.connect() as database:
                database.execute("UPDATE jobs SET available=0")
        row = self.water.records()[0]
        self.assertEqual((row["state"], row["attempts"], row["error"]), ("dead", 3, "ConnectionError"))
        self.assertIsNone(row["report"])

    def test_payload_and_sources_are_inert(self):
        sentinel = Path(self.temporary.name) / "must-not-exist"
        content = f"from pathlib import Path\nPath({str(sentinel)!r}).write_text('executed')\nexec(user_input)\n"
        self.sail.capture(signed(self.body), self.body)
        resolver = lambda *_arguments: ([{"path": "incoming.py", "content": content}], {"simulation": True})
        report = digest_once(self.water, resolver, self.model)
        self.assertFalse(sentinel.exists())
        self.assertFalse(report["patch_applied"])
        self.assertEqual(report["disposition"], "review_required")
        self.assertEqual(report["files"][0]["findings"][0]["rule"], "dynamic_execution")
        self.assertEqual(self.water.path.stat().st_mode & 0o777, 0o600)
        with self.water.connect() as database:
            stored = database.execute("SELECT sources FROM jobs").fetchone()[0]
        self.assertEqual(json.loads(stored)[0]["content"], content)
        self.assertEqual([path.name for path in Path(self.temporary.name).iterdir()], ["deep-water.sqlite3"])

    def test_traversal_and_unexpected_sources_fail_closed(self):
        for path in ["../escape.py", "/absolute.py", "safe/../../bad", ".git/config", "back\\slash"]:
            with self.assertRaises(ValueError):
                safe_path(path)
        self.sail.capture(signed(self.body), self.body)
        result = digest_once(self.water, lambda *_arguments: ([{"path": "../escape", "content": "x"}], {}), self.model)
        self.assertEqual(result["disposition"], "analysis_unavailable")

    def test_github_pins_contents_to_signed_commit_and_ignores_urls(self):
        source = GitHubSources([REPOSITORY])
        endpoints = []
        def get(endpoint):
            endpoints.append(endpoint)
            if "/compare/" in endpoint:
                return {"status": "ahead", "files": [{"filename": "service/read.py", "status": "modified"}]}
            return {"type": "file", "size": 12, "encoding": "base64", "content": base64.b64encode(b"print('hi')\n").decode()}
        source.get = get
        payload = json.loads(self.body)
        payload["repository"]["url"] = "http://169.254.169.254/"
        payload["files"] = [{"path": "evil.py", "content": "exec('ignored')"}]
        files, provenance = source("push", payload)
        self.assertEqual(files[0]["content"], "print('hi')\n")
        self.assertEqual(provenance["after"], "b" * 40)
        self.assertTrue(endpoints[-1].endswith("?ref=" + "b" * 40))
        self.assertTrue(all(endpoint.startswith("/repos/" + REPOSITORY) for endpoint in endpoints))

    def test_comparison_truncation_and_forks_require_review(self):
        source = GitHubSources([REPOSITORY])
        source.get = lambda _endpoint: {"status": "ahead", "files": [{"status": "removed"}] * 300}
        with self.assertRaises(ValueError):
            source("push", json.loads(self.body))
        payload = {"repository": {"full_name": REPOSITORY}, "action": "opened", "pull_request": {"head": {"repo": {"full_name": "fork/repo"}}}}
        with self.assertRaises(ValueError):
            source("pull_request", payload)

    def test_ping_does_not_queue(self):
        self.assertFalse(self.sail.capture(signed(self.body, event="ping"), self.body)["queued"])
        self.assertEqual(self.water.records(), [])

    def test_ai_routes_novel_benign_source_to_review(self):
        self.sail.capture(signed(self.body), self.body)
        content = "def format_pet(record):\n    return record.get('name')\n" * 1000
        report = digest_once(self.water, lambda *_arguments: ([{"path": "large.py", "content": content}], {}), self.model)
        self.assertEqual(report["files"][0]["findings"], [])
        self.assertEqual(report["disposition"], "novelty_review_required")

    def test_advisor_cannot_downgrade_configured_review(self):
        self.sail.capture(signed(self.body), self.body)
        class RoutineAdvisor:
            def review(self, _sources, _report):
                return {"review": {"priority": "routine"}}
        report = digest_once(self.water, lambda *_arguments: ([{"path": "danger.py", "content": "exec(source)"}], {}), self.model, RoutineAdvisor())
        self.assertEqual(report["disposition"], "review_required")

    def test_configured_advisor_failure_requires_retry(self):
        self.sail.capture(signed(self.body), self.body)
        class UnavailableAdvisor:
            def review(self, _sources, _report):
                raise TimeoutError("local inference unavailable")
        report = digest_once(self.water, lambda *_arguments: ([{"path": "source.py", "content": "return record"}], {}), self.model, UnavailableAdvisor())
        self.assertEqual(report["disposition"], "analysis_unavailable")
        self.assertEqual(self.water.records()[0]["state"], "pending")


if __name__ == "__main__":
    unittest.main()
