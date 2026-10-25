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
from .report_fonts import REPORT_FONT_CSS
from .report_theme import REPORT_CSS


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

    rows = "".join('<tr class="state-' + ("pass" if check["passed"] is True else "fail") + '"><td>' + escape(check["name"]) + "</td><td>" + ("PASS" if check["passed"] is True else "FAIL") + "</td></tr>" for check in evidence["checks"])
    files = "".join('<article class="scenario"><span class="scenario-number">SOURCE SCENARIO / ' + str(index + 1).zfill(2) + "</span><h3>" + escape(report["delivery"]) + '</h3><p class="disposition">' + escape(report["disposition"]) + "</p><p>" + escape(report["elapsed_ms"]) + " ms · " + escape(sum(len(item["findings"]) for item in report["files"])) + " configured rule signals</p></article>" for index, report in enumerate(evidence["reports"]))
    gemma_reports = [report for report in evidence["reports"] if report.get("gemma", {}).get("status") == "advisory"]
    passed = sum(check["passed"] is True for check in evidence["checks"])
    external = evidence.get("external_after")
    extra = ""
    if external:
        extra = "<h2>Private application verification</h2><pre>" + html.escape(json.dumps(external, indent=2)) + "</pre>"
    document = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="dark"><title>Cthulhu Daemon · measured simulation</title><style>""" + REPORT_FONT_CSS + REPORT_CSS + """</style></head><body>
<a class="skip" href="#main">Skip to measured report</a><header class="masthead"><div class="shell"><div class="masthead-inner"><a class="identity" href="#main"><span class="seal" aria-hidden="true"><svg viewBox="0 0 48 48" fill="none" stroke="currentColor" stroke-width=".9"><path d="M24 3 30 17 45 19 34 29 37 45 24 37 11 45 14 29 3 19 18 17Z"/><path d="m24 8 15 27H9Zm0 31L9 16h30Z"/><circle cx="24" cy="24" r="14"/><circle cx="24" cy="24" r="4"/></svg></span><span><span class="wordmark">CTHULHU DAEMON</span><span class="eyebrow" style="display:block">Repository current // evidence archive</span></span></a><div class="stamp"><b>SAVED EXECUTION REPORT</b><br>Run: """ + escape(evidence["generated_at"]) + """</div></div><nav class="nav" aria-label="Report sections"><a href="#scenarios">01 / Source scenarios</a><a href="#boundaries">02 / Boundary checks</a><a href="#rehearsal">03 / Virtual rehearsal</a><a href="#models">04 / Model reviews</a><a href="report.json">Raw evidence ↗</a></nav></div></header>
<main class="shell" id="main"><section class="hero" aria-labelledby="report-title"><div class="hero-copy"><span class="tag">SYNTHETIC INPUT · MEASURED EXECUTION</span><h1>Cthulhu Daemon</h1><p class="hook" id="report-title">Code flows in. Evidence surfaces.<br>You keep the final call.</p><p class="intro">A biomimetic code-assurance Symbiont. Signed ingress → inert queue → local AI review.</p><p class="intro">Virtual security rehearsals exercise a separate trusted fictional fixture, never captured source. This is a saved report, not live telemetry.</p></div><div class="stats" aria-label="Measured run overview"><div class="stat"><span class="stat-value">""" + str(passed) + "/" + str(len(evidence["checks"])) + """</span><span class="stat-label">Boundary assertions passed</span></div><div class="stat"><span class="stat-value">""" + str(len(evidence["reports"])) + """</span><span class="stat-label">Source scenarios</span></div><div class="stat"><span class="stat-value">""" + str(len(gemma_reports)) + """</span><span class="stat-label">Measured Gemma opinions</span></div><div class="stat"><span class="stat-value words">INERT DATA</span><span class="stat-label">Captured source handling</span></div></div></section>"""
    document += '<section id="scenarios" aria-labelledby="scenarios-heading"><div class="section-heading"><span class="section-index">01</span><h2 id="scenarios-heading">Observed source scenarios</h2></div><div class="scenario-grid">' + files + '</div></section><section id="boundaries" aria-labelledby="boundaries-heading"><div class="section-heading"><span class="section-index">02</span><h2 id="boundaries-heading">Boundary checks</h2></div><div class="boundary-layout"><div class="panel table-panel"><table aria-label="Observed boundary check results"><tbody>' + rows + """</tbody></table></div><aside class="side-stack" aria-label="Architecture and evidence boundaries"><div class="panel"><span class="tag secondary">THE SYMBIONT</span><h3 style="margin-top:16px">Six instincts. One bounded review.</h3><ul class="role-list"><li><b>Man o’ War</b> Signed webhook intake</li><li><b>Nutcracker</b> Structural novelty memory</li><li><b>Prairie dog</b> Review-signal triage</li><li><b>Dolphin</b> Local model rest</li><li><b>Wolf</b> Commit provenance</li><li><b>Beaver</b> Workflow resilience</li></ul></div><div class="panel"><h3>Evidence, not assurances</h3><p class="note">Synthetic input. Real execution. No automatic patches, production security guarantees, or candidate-code execution.</p><a class="button" href="report.json">Inspect measured JSON ↗</a><p class="note">The complete record preserves expected and observed outcomes, model opinions, and limitations.</p></div></aside></div></section>"""
    rehearsal = evidence.get("virtual_rehearsal")
    if rehearsal:
        document += '<section id="rehearsal" aria-labelledby="rehearsal-heading"><div class="section-heading"><span class="section-index">03</span><h2 id="rehearsal-heading">Virtual security-contract rehearsal</h2></div><p class="note">Beyond monitoring: these probes run over real loopback HTTP against a trusted fictional service. The negative controls deliberately break authorization or consent enforcement. They should fail the same probes that the secure fixture passes. This does not execute incoming code or certify an application.</p><div class="rehearsal-grid">'
        for case in [rehearsal["secure_fixture"], *rehearsal["negative_controls"]]:
            secure_case = case is rehearsal["secure_fixture"]
            label = ("SECURE FIXTURE: PASS" if case["assertions_passed"] else "SECURE FIXTURE: FAIL") if secure_case else ("NEGATIVE CONTROL: DETECTED" if case["detected_violations"] else "NEGATIVE CONTROL: MISSED")
            status_class = ("" if case["assertions_passed"] else " failed") if secure_case else (" control" if case["detected_violations"] else " failed")
            document += '<article class="rehearsal-card"><h3>' + escape(case["case_id"]) + '</h3><p class="status' + status_class + '">' + label + '</p><details><summary>Expected versus observed contract probes</summary><table aria-label="Contract probe results">'
            for probe in case["checks"]:
                document += "<tr><td>" + escape(probe["probe_id"]) + "</td><td>expected " + escape(probe["expected"]) + "; observed " + escape(probe["observed"]) + "</td></tr>"
            document += "</table></details></article>"
        document += '</div><small class="hash">Trusted fixture engine SHA-256: ' + escape(rehearsal["engine_source_sha256"]) + "</small></section>"
    else:
        document += '<section id="rehearsal"><div class="section-heading"><span class="section-index">03</span><h2>Virtual security-contract rehearsal</h2></div><p class="note">This saved run contains no virtual rehearsal record.</p></section>'
    document += extra + '<section id="models" aria-labelledby="models-heading"><div class="section-heading"><span class="section-index">04</span><h2 id="models-heading">Open-source AI · bounded opinions</h2></div><p class="note">' + escape(evidence["model"]["engine"] + " " + evidence["model"]["version"]) + " runs locally. Its novelty score is advisory; configured text rules produce review signals. This is not proof of security.</p>"
    if gemma_reports:
        document += '<p class="note">Measured Gemma reviews · unverified model opinions. Human review is required. The benign and novel-module fixtures contain no injected vulnerability; any model risk claims about those fixtures are false positives in this demonstration. These summaries trigger no automatic patches or execution.</p><div class="model-grid">'
        for report in gemma_reports:
            advisor = report["gemma"]
            document += '<article class="model-card"><h3>' + escape(report["delivery"] + " · " + advisor["model"]) + '</h3><p>' + escape(advisor["review"]["summary"]) + '</p><p class="metrics">' + escape(advisor["prompt_tokens"]) + " input tokens · " + escape(advisor["output_tokens"]) + " output tokens · " + escape(advisor["elapsed_ms"]) + " ms</p><small>Model digest: " + escape(advisor["model_digest"]) + "</small></article>"
        document += "</div>"
    else:
        document += "<p>This run contains no LLM inference.</p>"
    document += '</section><footer class="footer"><div><p>Code flows in. Evidence surfaces. You keep the final call.</p><small>Cthulhu Daemon // a biomimetic code-assurance Symbiont</small></div><div><a href="report.json">Full measured evidence ↗</a><small>Ingress mean: ' + escape(evidence["ingress_latency_ms"]["mean"]) + " ms.</small></div><small>Results use four fictional source scenarios; no production security outcomes or human time savings are inferred.</small></footer></main></body></html>"
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
