import tempfile
import unittest
from pathlib import Path

from creeper.simulate import render


class EvidenceRendererTests(unittest.TestCase):
    def evidence(self):
        return {"generated_at": "2026-10-25T00:00:00Z", "checks": [
            {"name": "passing fixture", "passed": True}, {"name": "failing fixture", "passed": False}],
            "reports": [{"delivery": "fixture", "disposition": "review_required", "elapsed_ms": 1,
                         "files": [{"findings": []}], "gemma": {
                             "status": "advisory", "model": "gemma3:1b", "model_digest": "a" * 64,
                             "review": {"summary": "Fixture only"}, "prompt_tokens": 10,
                             "output_tokens": 5, "elapsed_ms": 1}}],
            "model": {"engine": "fixture", "version": "test"}, "ingress_latency_ms": {"mean": 1}}

    def document(self, evidence):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "report.html"
            render(evidence, path)
            return path.read_text()

    def test_check_results_are_not_hardcoded_as_passing(self):
        document = self.document(self.evidence())
        self.assertIn("<td>passing fixture</td><td>PASS</td>", document)
        self.assertIn("<td>failing fixture</td><td>FAIL</td>", document)

    def test_dynamic_metrics_are_escaped_even_when_evidence_is_malformed(self):
        evidence = self.evidence()
        attack = "<script>alert('fixture')</script>"
        evidence["reports"][0]["elapsed_ms"] = attack
        evidence["reports"][0]["gemma"]["prompt_tokens"] = attack
        evidence["reports"][0]["gemma"]["output_tokens"] = attack
        evidence["reports"][0]["gemma"]["elapsed_ms"] = attack
        evidence["ingress_latency_ms"]["mean"] = attack
        document = self.document(evidence)
        self.assertNotIn("<script>", document)
        self.assertEqual(document.count("&lt;script&gt;"), 5)


if __name__ == "__main__":
    unittest.main()
