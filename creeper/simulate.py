import argparse
import hashlib
import hmac
import html
import json
import secrets
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from .__main__ import make_server
from .digest import SpatialModel, digest_once
from .ingress import DeepWater, Sail


REPOSITORY = "simulation/fictional-clinic"


def run(output, before=None, after=None, additional_sources=None, reviewer=None):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    output.chmod(0o700)
    secret = secrets.token_hex(32)
    water = DeepWater(output / "state")
    if water.records():
        raise ValueError("Use a fresh evidence directory for every simulation")
    sail = Sail(water, secret, [REPOSITORY])
    server = make_server(sail, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    address = "http://127.0.0.1:" + str(server.server_port) + "/webhooks/github"
    model = SpatialModel()
    sentinel = output / "PAYLOAD_MUST_NOT_EXECUTE"
    scenarios = {
        "benign": [{"path": "clinic/read.py", "content": "def display_pet(record):\n    return record.get('name', 'SIMULATION')\n"}],
        "sql-risk": [{"path": "clinic/query.py", "content": "def lookup(name):\n    return f\"SELECT * FROM pets WHERE name='{name}'\"\n"}],
        "executable-payload": [{"path": "clinic/import.py", "content": "from pathlib import Path\n" + f"Path({str(sentinel)!r}).write_text('executed')\n" + "import subprocess\nsubprocess.run(user_input, shell=True)\nexec(untrusted_source)\n"}],
    }
    scenarios["novel-module"] = [{"path": "clinic/large_module.py", "content": "def format_pet(record):\n    return record.get('name')\n" * 1000}]
    if additional_sources:
        scenarios["private-source-snapshot"] = additional_sources
    checks = []
    timings = []
    reports = []

    def check(name, observed, expected):
        checks.append({"name": name, "observed": observed, "expected": expected, "passed": observed == expected})
        if observed != expected:
            raise AssertionError(name)

    def send(delivery, case, valid=True, repository=REPOSITORY):
        payload = {"repository": {"full_name": repository}, "before": "a" * 40, "after": "b" * 40,
                   "simulation_case": case}
        body = json.dumps(payload, sort_keys=True).encode()
        signature = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        request = urllib.request.Request(address, data=body, headers={"Content-Type": "application/json",
            "X-GitHub-Event": "push", "X-GitHub-Delivery": delivery,
            "X-Hub-Signature-256": signature if valid else "sha256=" + "0" * 64})
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                status, result = response.status, json.load(response)
        except urllib.error.HTTPError as error:
            status, result = error.code, json.load(error)
        timings.append(round((time.perf_counter() - started) * 1000, 3))
        return status, result

    def resolver(_event, payload):
        return scenarios[payload["simulation_case"]], {"simulation": True, "coverage": "explicit_synthetic_fixtures", "repository": REPOSITORY}

    external_before = None
    external_after = None
    try:
        external_before = before() if before else None
        check("invalid HMAC rejected over HTTP", send("bad-signature", "benign", valid=False)[0], 401)
        check("wrong repository rejected over HTTP", send("wrong-repo", "benign", repository="other/repo")[0], 403)
        for case in scenarios:
            check(case + " durably accepted over HTTP", send(case, case)[0], 202)
        check("duplicate delivery acknowledged", send("benign", "benign")[1]["duplicate"], True)
        check("mismatched replay rejected", send("benign", "sql-risk")[0], 409)
        water = DeepWater(output / "state")
        check("pending queue survives reopening", len(water.records()), len(scenarios))
        for _case in scenarios:
            reports.append(digest_once(water, resolver, model, reviewer=reviewer))
        check("all jobs complete", [row["state"] for row in water.records()], ["done"] * len(scenarios))
        check("benign source has no configured rule match", len(reports[0]["files"][0]["findings"]), 0)
        check("interpolated SQL requires review", reports[1]["disposition"], "review_required")
        check("executable source requires review", reports[2]["disposition"], "review_required")
        check("AI routes a novel module for review without alleging a vulnerability", reports[3]["disposition"], "novelty_review_required")
        check("payload did not create its sentinel", sentinel.exists(), False)
        check("no automatic patches claimed", any(report["patch_applied"] for report in reports), False)
        external_after = after() if after else None
        evidence = {"generated_at": datetime.now(timezone.utc).isoformat(), "mode": "synthetic_data_real_execution",
                    "transport": "real loopback HTTP with GitHub-style HMAC-SHA256",
                    "github_delivery": "synthetic; no real GitHub webhook claimed", "model": model.provenance,
                    "checks": checks, "reports": reports,
                    "ingress_latency_ms": {"count": len(timings), "max": max(timings), "mean": round(sum(timings) / len(timings), 3)},
                    "external_before": external_before, "external_after": external_after,
                    "limitations": ["Four synthetic scenarios plus any supplied private snapshot; not an accuracy benchmark",
                                    "No verified zero-days, automatic patching, or production isolation claimed",
                                    "A data-only queue is not an OS execution sandbox"]}
        path = output / "report.json"
        path.write_text(json.dumps(evidence, indent=2) + "\n")
        path.chmod(0o600)
        render(evidence, output / "report.html")
        return evidence
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def render(evidence, path):
    rows = "".join("<tr><td>" + html.escape(check["name"]) + "</td><td>PASS</td></tr>" for check in evidence["checks"])
    files = "".join("<article><h3>" + html.escape(report["delivery"]) + "</h3><p>" + html.escape(report["disposition"]) + "</p><p>" + str(report["elapsed_ms"]) + " ms · " + str(sum(len(item["findings"]) for item in report["files"])) + " configured rule signals</p></article>" for report in evidence["reports"])
    external = evidence.get("external_after")
    extra = ""
    if external:
        extra = "<h2>Private application verification</h2><pre>" + html.escape(json.dumps(external, indent=2)) + "</pre>"
    document = """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Creeper · measured simulation</title>
<style>body{margin:0;background:#071b20;color:#d9eeeb;font:16px system-ui;line-height:1.6}main{max-width:1000px;margin:auto;padding:48px 24px}h1{font-size:40px;line-height:1.1}h2{margin-top:40px;color:#77d6bb}small{color:#9fc1bb}.tag{border:1px solid #77d6bb;border-radius:40px;padding:8px 15px;color:#77d6bb}section{display:flex;gap:16px;flex-wrap:wrap}article{background:#123139;padding:20px;flex:1;min-width:200px;border-radius:12px}table{width:100%;border-collapse:collapse}td{border-bottom:1px solid #285059;padding:12px}td:last-child{color:#77d6bb}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#123139;padding:20px;border-radius:12px}a{color:#77d6bb}</style>
<main><span class="tag">SYNTHETIC INPUT · MEASURED EXECUTION</span><h1>The current carries the work.</h1><p>Man o’ War orchestration: signed ingress → inert deep-water queue → local AI digestion → review report.</p>"""
    document += "<small>Run: " + html.escape(evidence["generated_at"]) + "</small><h2>Observed source scenarios</h2><section>" + files + "</section><h2>Boundary checks</h2><table>" + rows + "</table>"
    document += extra + "<h2>Open-source AI</h2><p>" + html.escape(evidence["model"]["engine"] + " " + evidence["model"]["version"]) + " runs locally. Its novelty score is advisory; configured text rules produce review signals. This is not proof of security.</p>"
    gemma_reports = [report for report in evidence["reports"] if report.get("gemma", {}).get("status") == "advisory"]
    if gemma_reports:
        document += "<h2>Measured Gemma reviews · unverified model opinions</h2><p>Human review is required. The benign and novel-module fixtures contain no injected vulnerability; any model risk claims about those fixtures are false positives in this demonstration. These summaries trigger no automatic patches or execution.</p>"
        for report in gemma_reports:
            advisor = report["gemma"]
            document += "<article><h3>" + html.escape(report["delivery"] + " · " + advisor["model"]) + "</h3><p>" + html.escape(advisor["review"]["summary"]) + "</p><p>" + str(advisor["prompt_tokens"]) + " input tokens · " + str(advisor["output_tokens"]) + " output tokens · " + str(advisor["elapsed_ms"]) + " ms</p><small>Model digest: " + html.escape(advisor["model_digest"]) + "</small></article>"
    else:
        document += "<p>This run contains no LLM inference.</p>"
    document += "<p>Ingress mean: " + str(evidence["ingress_latency_ms"]["mean"]) + " ms. Results use four fictional source scenarios; no production security outcomes or human time savings are inferred.</p><p><a href='report.json'>Full measured evidence</a></p></main></html>"
    Path(path).write_text(document)
    Path(path).chmod(0o600)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="evidence/simulation-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S"))
    parser.add_argument("--gemma-model")
    arguments = parser.parse_args()
    from .gemma import GemmaReviewer
    reviewer = GemmaReviewer(arguments.gemma_model) if arguments.gemma_model else None
    evidence = run(arguments.output, reviewer=reviewer)
    print(json.dumps({"checks_passed": len(evidence["checks"]), "output": arguments.output}, indent=2))


if __name__ == "__main__":
    main()
