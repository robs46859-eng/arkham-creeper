import hashlib
import json
import re
import time

from .source import validate_sources


RULES = [
    ("shell_execution", re.compile(r"shell\s*=\s*True"), "Review shell construction; use a fixed executable and argument list."),
    ("sql_interpolation", re.compile(r"(?:f[\"']|`)[^\n]*(?:SELECT|INSERT|UPDATE|DELETE)[^\n]*(?:\{|\$\{)", re.I), "Use parameterized SQL; validate tenant and consent independently."),
    ("dynamic_execution", re.compile(r"\b(?:eval|exec)\s*\("), "Remove dynamic evaluation of untrusted content."),
]


def features(content):
    return [len(content), len(content.splitlines()), content.count("import "), content.count("("),
            content.count("{"), content.count("return "), *[len(pattern.findall(content)) for _, pattern, _ in RULES]]


class SpatialModel:
    def __init__(self):
        import sklearn
        from sklearn.ensemble import IsolationForest
        baseline = []
        templates = [
            "def read_record(record):\n    return record.get('name', 'SIMULATION')\n",
            "import json\ndef encode(data):\n    return json.dumps(data)\n",
            "export function readRecord(record) { return record.name; }\n",
            "const record = {name: 'SIMULATION', species: 'dog'};\n",
        ]
        for index in range(1, 121):
            text = templates[index % len(templates)] * index
            baseline.append(features(text))
        self.model = IsolationForest(n_estimators=64, contamination=0.05, random_state=42).fit(baseline)
        self.provenance = {"engine": "scikit-learn IsolationForest", "version": sklearn.__version__, "seed": 42,
                           "training": "120 generated benign snippets; synthetic baseline only",
                           "training_sha256": hashlib.sha256(json.dumps(baseline).encode()).hexdigest(),
                           "meaning": "Novelty signal, not vulnerability verification or a security accuracy benchmark"}

    def score(self, content):
        vector = features(content)
        return {"features": vector, "anomalous": bool(self.model.predict([vector])[0] == -1),
                "score": float(self.model.decision_function([vector])[0])}


def digest_once(water, resolver, model, reviewer=None):
    job = water.claim()
    if job is None:
        return None
    started = time.perf_counter()
    try:
        payload = json.loads(job["payload"])
        sources, provenance = resolver(job["event"], payload)
        validate_sources(sources)
        water.store_sources(job, sources)
        reports = []
        for source in sources:
            content = source["content"]
            findings = []
            for rule, pattern, recommendation in RULES:
                for match in pattern.finditer(content):
                    findings.append({"rule": rule, "line": content.count("\n", 0, match.start()) + 1,
                                     "status": "review_required", "recommendation": recommendation})
            reports.append({"path": source["path"], "sha256": hashlib.sha256(content.encode()).hexdigest(),
                            "bytes": len(content.encode()), "spatial": model.score(content), "findings": findings})
        disposition = "no_configured_rule_match"
        if any(item["spatial"]["anomalous"] for item in reports):
            disposition = "novelty_review_required"
        if any(item["findings"] for item in reports):
            disposition = "review_required"
        report = {"delivery": job["delivery"], "source": provenance, "files": reports, "model": model.provenance,
                  "disposition": disposition,
                  "execution": "source stored and examined as data; never imported, evaluated, or written as executable files",
                  "patch_applied": False, "elapsed_ms": round((time.perf_counter() - started) * 1000, 3)}
        if reviewer is not None:
            report["gemma"] = reviewer.review(sources, report)
            if disposition == "no_configured_rule_match" and report["gemma"].get("review", {}).get("priority") == "review":
                report["disposition"] = "advisory_review_required"
            report["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 3)
        water.finish(job, report=report)
        return report
    except Exception as error:
        water.finish(job, error=type(error).__name__)
        return {"delivery": job["delivery"], "disposition": "analysis_unavailable", "error": type(error).__name__}
