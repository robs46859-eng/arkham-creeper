import json
import unittest
from unittest.mock import patch

from creeper.gemma import GemmaReviewer, IncompleteReview


class GemmaBoundaryTests(unittest.TestCase):
    def test_remote_or_non_gemma_model_tag_is_rejected(self):
        for model in ["http://remote/model", "llama3:1b", "gemma3", "gemma3:1b\n"]:
            with self.assertRaises(ValueError):
                GemmaReviewer(model)

    def reviewer(self, output=None):
        captured = []
        def request(_reviewer, path, payload=None):
            captured.append((path, payload))
            if path == "/api/tags":
                return {"models": [{"name": "gemma3:1b", "digest": "a" * 64}]}
            if path == "/api/show":
                return {"details": {"family": "gemma3"}}
            if path == "/api/version":
                return {"version": "test-fixture"}
            if path == "/api/ps":
                return {"models": []}
            return {"model": "gemma3:1b", "done": True, "response": json.dumps(output or {
                "priority": "review", "summary": "Test fixture only", "recommendations": ["Review parameter binding"]}),
                "prompt_eval_count": 100, "eval_count": 20}
        return captured, request

    def test_bounded_excerpts_and_unload_are_observed(self):
        captured, request = self.reviewer()
        with patch.object(GemmaReviewer, "request", request):
            reviewer = GemmaReviewer("gemma3:1b")
            sources = [{"path": "source.py", "content": "untrusted" * 1000}] * 4
            report = {"files": [{"findings": [], "spatial": {"anomalous": False}}] * 4}
            result = reviewer.review(sources, report)
        generated = next(payload for path, payload in captured if path == "/api/generate")
        self.assertEqual(generated["keep_alive"], 0)
        self.assertNotIn("tools", generated)
        self.assertEqual(result["selected_files"], 3)
        self.assertTrue(result["unloaded_after_review"])
        self.assertEqual(result["model_digest"], "a" * 64)
        self.assertEqual(result["prompt_tokens"], 100)
        self.assertLess(len(generated["prompt"]), 5000)

    def test_malformed_recommendations_are_rejected(self):
        captured, request = self.reviewer({"priority": "review", "summary": "Invalid fixture", "recommendations": {"execute": "ignored"}})
        with patch.object(GemmaReviewer, "request", request):
            reviewer = GemmaReviewer("gemma3:1b")
            with self.assertRaises(ValueError):
                reviewer.review([{"path": "source.py", "content": "text"}], {"files": [{"findings": [], "spatial": {"anomalous": False}}]})

    def test_truncated_generation_is_not_a_completed_review(self):
        captured, request = self.reviewer()
        def truncated(reviewer, path, payload=None):
            result = request(reviewer, path, payload)
            if path == "/api/generate":
                result.update({"done_reason": "length", "response": '{"summary":'})
            return result
        with patch.object(GemmaReviewer, "request", truncated):
            reviewer = GemmaReviewer("gemma3:1b")
            with self.assertRaises(IncompleteReview):
                reviewer.review([{"path": "source.py", "content": "text"}], {"files": [{"findings": [], "spatial": {"anomalous": False}}]})


if __name__ == "__main__":
    unittest.main()
