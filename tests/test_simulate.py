import copy
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path

from creeper.simulate import render


class ReportMarkup(HTMLParser):
    def __init__(self, document):
        super().__init__()
        self.elements = []
        self.feed(document)

    def handle_starttag(self, tag, attributes):
        self.elements.append((tag, dict(attributes)))


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

    def test_theme_rendering_does_not_rewrite_measured_evidence(self):
        evidence = self.evidence()
        original = copy.deepcopy(evidence)
        self.document(evidence)
        self.assertEqual(evidence, original)

    def test_theme_fonts_are_embedded_without_remote_runtime_dependencies(self):
        document = self.document(self.evidence())
        elements = ReportMarkup(document).elements
        self.assertFalse(any(tag == "script" for tag, _attributes in elements))
        self.assertFalse(any(tag == "link" and "stylesheet" in attributes.get("rel", "").split()
                             for tag, attributes in elements))
        self.assertIn("data:font/woff2;base64,", document)
        for family in ["Cinzel", "JetBrains Mono", "Space Mono"]:
            self.assertIn(family, document)

    def test_report_landmarks_keep_saved_simulation_identity(self):
        evidence = self.evidence()
        evidence["virtual_rehearsal"] = {
            "secure_fixture": {"case_id": "secure-fixture", "assertions_passed": True, "checks": []},
            "negative_controls": [], "engine_source_sha256": "b" * 64}
        document = self.document(evidence)
        elements = ReportMarkup(document).elements
        identifiers = {attributes.get("id") for _tag, attributes in elements}
        self.assertTrue({"scenarios", "boundaries", "rehearsal", "models"}.issubset(identifiers))
        self.assertTrue(any(tag == "main" for tag, _attributes in elements))
        self.assertIn("<h1>Cthulhu Daemon</h1>", document)
        self.assertIn("<title>Cthulhu Daemon · measured simulation</title>", document)
        self.assertIn("SYNTHETIC INPUT", document)
        self.assertIn("saved", document.lower())

    def test_failed_rehearsal_and_missed_control_are_not_styled_as_success(self):
        evidence = self.evidence()
        evidence["virtual_rehearsal"] = {
            "secure_fixture": {"case_id": "secure-fixture", "assertions_passed": False, "checks": []},
            "negative_controls": [{"case_id": "missed-control", "detected_violations": [], "checks": []}],
            "engine_source_sha256": "b" * 64}
        document = self.document(evidence)
        self.assertIn("SECURE FIXTURE: FAIL", document)
        self.assertIn("NEGATIVE CONTROL: MISSED", document)
        self.assertNotIn("SECURE FIXTURE: PASS", document)
        self.assertNotIn("NEGATIVE CONTROL: DETECTED", document)


if __name__ == "__main__":
    unittest.main()
