import hashlib
import hmac
import json
import tempfile
import unittest

from creeper.digest import MAX_FINDINGS_PER_FILE, RULES, SpatialModel, digest_once, features
from creeper.ingress import DeepWater, Sail


class ReviewRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = SpatialModel()

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.water = DeepWater(self.temporary.name)
        secret = "review-regression-test-secret-32-characters"
        body = json.dumps({"repository": {"full_name": "example/review"}}).encode()
        headers = {"X-GitHub-Delivery": "review-job", "X-GitHub-Event": "push",
                   "X-Hub-Signature-256": "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()}
        Sail(self.water, secret, ["example/review"]).capture(headers, body)

    def test_reclaimed_sources_cannot_report_success(self):
        claimed = []
        def resolver(_event, _payload):
            with self.water.connect() as database:
                database.execute("UPDATE jobs SET lease_until=0")
            claimed.append(self.water.claim())
            return [{"path": "record.py", "content": "return record"}], {}
        result = digest_once(self.water, resolver, self.model)
        self.assertEqual(result["error"], "LeaseLost")
        self.assertEqual(result["disposition"], "analysis_unavailable")
        row = self.water.records()[0]
        self.assertEqual(row["state"], "processing")
        self.assertIsNone(row["report"])
        self.assertTrue(self.water.finish(claimed[0], report={"current": True}))

    def test_reclaimed_final_report_cannot_report_success(self):
        class ReclaimingAdvisor:
            def review(advisor, _sources, _report):
                with self.water.connect() as database:
                    database.execute("UPDATE jobs SET lease_until=0")
                self.water.claim()
                return {"review": {"priority": "routine"}}
        result = digest_once(self.water, lambda *_arguments: ([{"path": "record.py", "content": "return record"}], {}),
                             self.model, ReclaimingAdvisor())
        self.assertEqual(result["error"], "LeaseLost")
        self.assertIsNone(self.water.records()[0]["report"])

    def test_repeated_findings_are_counted_without_unbounded_reports(self):
        occurrences = MAX_FINDINGS_PER_FILE + 1000
        content = "eval(value)\n" * occurrences
        result = digest_once(self.water, lambda *_arguments: ([{"path": "repeated.py", "content": content}], {}), self.model)
        report = result["files"][0]
        self.assertEqual(len(report["findings"]), MAX_FINDINGS_PER_FILE)
        self.assertEqual(report["finding_count"], occurrences)
        self.assertTrue(report["findings_truncated"])
        self.assertEqual(result["disposition"], "review_required")

    def test_sql_rule_handles_long_lines_and_keeps_ordering(self):
        pattern = next(pattern for name, pattern, _recommendation in RULES if name == "sql_interpolation")
        self.assertFalse(pattern.search('f"' * 60000))
        self.assertFalse(pattern.search('f"' + 'SELECT ' * 18000))
        self.assertFalse(pattern.search('{value} f"SELECT fixed'))
        self.assertFalse(pattern.search('SELECT fixed f"{value}'))
        self.assertTrue(pattern.search('return f"SELECT * FROM pets WHERE name={name}"'))
        self.assertEqual(features('f"SELECT {value}"\nf"UPDATE {value}"')[-2], 2)


if __name__ == "__main__":
    unittest.main()
