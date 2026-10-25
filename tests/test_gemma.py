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
            return {"model": "gemma3:1b", "done": True, "response": json.dumps(output if output is not None else {
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

    def test_repeated_findings_unicode_and_paths_cannot_overflow_prompt(self):
        captured, request = self.reviewer()
        path = "clinic/" + "獣" * 1000 + ".py"
        sources = [{"path": path, "content": "獣\x01" * 3000}] * 3
        report = {"files": [{"findings": [{"rule": "dynamic_execution"}] * 16000,
                             "spatial": {"anomalous": True}}] * 3}
        with patch.object(GemmaReviewer, "request", request):
            result = GemmaReviewer("gemma3:1b").review(sources, report)
        generated = next(payload for endpoint, payload in captured if endpoint == "/api/generate")
        excerpts = json.loads(generated["prompt"].split("\n", 1)[1])
        self.assertLessEqual(len(generated["prompt"].encode()), 2000)
        self.assertEqual(generated["options"]["num_ctx"], 4096)
        self.assertTrue(all(len(item["path"].encode()) <= 160 for item in excerpts))
        self.assertTrue(all(item["configured_findings"] == ["dynamic_execution"] for item in excerpts))
        self.assertEqual(result["truncated_files"], [path] * 3)
        self.assertEqual(result["truncated_prompt_paths"], [path] * 3)
        self.assertEqual(result["excerpt_characters"], [len(item["untrusted_code"]) for item in excerpts])
        self.assertTrue(all(0 < count <= 1200 for count in result["excerpt_characters"]))

    def test_output_must_match_requested_schema_limits(self):
        for output in [
            {"priority": "review", "summary": "x" * 801, "recommendations": []},
            {"priority": "review", "summary": "fixture", "recommendations": ["x" * 301]},
            {"priority": "review", "summary": "fixture", "recommendations": ["x"] * 4},
        ]:
            with self.subTest(output=output):
                _captured, request = self.reviewer(output)
                with patch.object(GemmaReviewer, "request", request):
                    reviewer = GemmaReviewer("gemma3:1b")
                    with self.assertRaises(ValueError):
                        reviewer.review([{"path": "source.py", "content": "text"}], {"files": [{"findings": [], "spatial": {"anomalous": False}}]})

    def test_changed_model_digest_is_rejected_before_or_after_inference(self):
        for changed_request in [2, 3]:
            with self.subTest(changed_request=changed_request):
                captured, request = self.reviewer()
                tag_requests = []
                def drift(reviewer, path, payload=None):
                    result = request(reviewer, path, payload)
                    if path == "/api/tags":
                        tag_requests.append(path)
                        if len(tag_requests) == changed_request:
                            result["models"][0]["digest"] = "b" * 64
                    return result
                with patch.object(GemmaReviewer, "request", drift):
                    reviewer = GemmaReviewer("gemma3:1b")
                    with self.assertRaises(ValueError):
                        reviewer.review([{"path": "source.py", "content": "text"}], {"files": [{"findings": [], "spatial": {"anomalous": False}}]})
                self.assertEqual(sum(path == "/api/generate" for path, _payload in captured), changed_request - 2)

    def test_malformed_token_counts_are_rejected(self):
        for field in ["prompt_eval_count", "eval_count"]:
            for count in [None, True, -1, "<script>fixture</script>"]:
                with self.subTest(field=field, count=count):
                    _captured, request = self.reviewer()
                    def malformed(reviewer, path, payload=None):
                        result = request(reviewer, path, payload)
                        if path == "/api/generate":
                            result[field] = count
                        return result
                    with patch.object(GemmaReviewer, "request", malformed):
                        reviewer = GemmaReviewer("gemma3:1b")
                        with self.assertRaises(ValueError):
                            reviewer.review([{"path": "source.py", "content": "text"}], {"files": [{"findings": [], "spatial": {"anomalous": False}}]})


if __name__ == "__main__":
    unittest.main()
