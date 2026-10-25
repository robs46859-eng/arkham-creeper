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
from .rehearse import run_rehearsal


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
    model = SpatialModel()
    server = make_server(sail, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    address = "http://127.0.0.1:" + str(server.server_port) + "/webhooks/github"
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
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

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
            with opener.open(request, timeout=10) as response:
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
        rehearsal = run_rehearsal()
        check("virtual security contracts pass in secure fixture", rehearsal["secure_fixture"]["assertions_passed"], True)
        check("both deliberately faulty negative controls are detected", rehearsal["both_controls_detected"], True)
        external_after = after() if after else None
        evidence = {"generated_at": datetime.now(timezone.utc).isoformat(), "mode": "synthetic_data_real_execution",
                    "transport": "real loopback HTTP with GitHub-style HMAC-SHA256",
                    "github_delivery": "synthetic; no real GitHub webhook claimed", "model": model.provenance,
                    "checks": checks, "reports": reports, "virtual_rehearsal": rehearsal,
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
    def escape(value):
        return html.escape(str(value))

    rows = "".join("<tr><td>" + escape(check["name"]) + "</td><td>" + ("PASS" if check["passed"] is True else "FAIL") + "</td></tr>" for check in evidence["checks"])
    files = "".join("<article><h3>" + escape(report["delivery"]) + "</h3><p>" + escape(report["disposition"]) + "</p><p>" + escape(report["elapsed_ms"]) + " ms · " + escape(sum(len(item["findings"]) for item in report["files"])) + " configured rule signals</p></article>" for report in evidence["reports"])
    external = evidence.get("external_after")
    extra = ""
    if external:
        extra = "<h2>Private application verification</h2><pre>" + html.escape(json.dumps(external, indent=2)) + "</pre>"
    document = """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Creeper · measured simulation</title>
<style>body{margin:0;background:#071b20;color:#d9eeeb;font:16px system-ui;line-height:1.6}main{max-width:1000px;margin:auto;padding:48px 24px}h1{font-size:40px;line-height:1.1}h2{margin-top:40px;color:#77d6bb}small{color:#9fc1bb;overflow-wrap:anywhere}.tag{border:1px solid #77d6bb;border-radius:40px;padding:8px 15px;color:#77d6bb}section{display:flex;gap:16px;flex-wrap:wrap}article{background:#123139;padding:20px;flex:1;min-width:200px;border-radius:12px}table{width:100%;border-collapse:collapse}td{border-bottom:1px solid #285059;padding:12px}td:last-child{color:#77d6bb}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#123139;padding:20px;border-radius:12px}a{color:#77d6bb}</style>
<main><span class="tag">SYNTHETIC INPUT · MEASURED EXECUTION</span><h1>The current carries the work.</h1><p>A biomimetic Symbiont: Man o’ War intake, nutcracker-inspired novelty memory, prairie-dog signal triage, dolphin model rest, wolf-like provenance, and beaver-like workflow resilience.</p><p>Signed ingress → inert queue → local AI review. Virtual security rehearsals exercise a separate trusted fictional fixture, never captured source.</p>"""
    document += "<small>Run: " + escape(evidence["generated_at"]) + "</small><h2>Observed source scenarios</h2><section>" + files + "</section><h2>Boundary checks</h2><table>" + rows + "</table>"
    rehearsal = evidence.get("virtual_rehearsal")
    if rehearsal:
        document += "<h2>Beyond monitoring: virtual security-contract rehearsal</h2><p>These probes run over real loopback HTTP against a trusted fictional service. The negative controls deliberately break authorization or consent enforcement. They should fail the same probes that the secure fixture passes. This does not execute incoming code or certify an application.</p>"
        for case in [rehearsal["secure_fixture"], *rehearsal["negative_controls"]]:
            secure_case = case is rehearsal["secure_fixture"]
            label = ("SECURE FIXTURE: PASS" if case["assertions_passed"] else "SECURE FIXTURE: FAIL") if secure_case else ("NEGATIVE CONTROL: DETECTED" if case["detected_violations"] else "NEGATIVE CONTROL: MISSED")
            document += "<article><h3>" + escape(case["case_id"]) + "</h3><p>" + label + "</p><details><summary>Expected versus observed contract probes</summary><table>"
            for probe in case["checks"]:
                document += "<tr><td>" + escape(probe["probe_id"]) + "</td><td>expected " + escape(probe["expected"]) + "; observed " + escape(probe["observed"]) + "</td></tr>"
            document += "</table></details></article>"
        document += "<small>Trusted fixture engine SHA-256: " + escape(rehearsal["engine_source_sha256"]) + "</small>"
    document += extra + "<h2>Open-source AI</h2><p>" + escape(evidence["model"]["engine"] + " " + evidence["model"]["version"]) + " runs locally. Its novelty score is advisory; configured text rules produce review signals. This is not proof of security.</p>"
    gemma_reports = [report for report in evidence["reports"] if report.get("gemma", {}).get("status") == "advisory"]
    if gemma_reports:
        document += "<h2>Measured Gemma reviews · unverified model opinions</h2><p>Human review is required. The benign and novel-module fixtures contain no injected vulnerability; any model risk claims about those fixtures are false positives in this demonstration. These summaries trigger no automatic patches or execution.</p>"
        for report in gemma_reports:
            advisor = report["gemma"]
            document += "<article><h3>" + escape(report["delivery"] + " · " + advisor["model"]) + "</h3><p>" + escape(advisor["review"]["summary"]) + "</p><p>" + escape(advisor["prompt_tokens"]) + " input tokens · " + escape(advisor["output_tokens"]) + " output tokens · " + escape(advisor["elapsed_ms"]) + " ms</p><small>Model digest: " + escape(advisor["model_digest"]) + "</small></article>"
    else:
        document += "<p>This run contains no LLM inference.</p>"
    document += "<p>Ingress mean: " + escape(evidence["ingress_latency_ms"]["mean"]) + " ms. Results use four fictional source scenarios; no production security outcomes or human time savings are inferred.</p><p><a href='report.json'>Full measured evidence</a></p><p><strong>Push your code. Let the current carry the busywork. Keep the final call.</strong></p></main></html>"
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
