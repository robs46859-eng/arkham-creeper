import hashlib
import json
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .source import NoRedirect


def _run_case(case_id):
    record = {"id": "fictional-pet-001", "tenant": "fictional-clinic-alpha", "note": "baseline"}
    consent = {"active": True}

    class Handler(BaseHTTPRequestHandler):
        def respond(self, status, payload):
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def handle_request(self, write=False):
            token = self.headers.get("Authorization")
            if token not in {"Bearer fictional-owner", "Bearer fictional-outsider"}:
                return self.respond(401, {"error": "unauthenticated"})
            if token == "Bearer fictional-outsider" and case_id != "cross_tenant_bypass":
                return self.respond(403, {"error": "wrong_tenant"})
            if self.path == "/consent/revoke" and write:
                consent["active"] = False
                return self.respond(200, {"consent_active": False})
            if self.path != "/records/fictional-pet-001":
                return self.respond(404, {"error": "not_found"})
            if write:
                if not consent["active"] and case_id != "consent_bypass":
                    return self.respond(403, {"error": "consent_required"})
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if not 0 < length <= 4096:
                        raise ValueError("invalid_length")
                    payload = json.loads(self.rfile.read(length))
                    if not isinstance(payload.get("note"), str):
                        raise ValueError("invalid_note")
                except (ValueError, AttributeError):
                    return self.respond(400, {"error": "invalid_payload"})
                record["note"] = payload["note"]
            return self.respond(200, {"record": dict(record), "consent_active": consent["active"]})

        def do_GET(self):
            self.handle_request()

        def do_POST(self):
            self.handle_request(write=True)

        def log_message(self, *_arguments):
            pass

    checks = []

    def request(token=None, note=None, path="/records/fictional-pet-001"):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = "Bearer " + token
        body = json.dumps({"note": note}).encode() if note is not None else None
        outgoing = urllib.request.Request(address + path, data=body, headers=headers)
        try:
            with opener.open(outgoing, timeout=5) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as error:
            with error:
                return error.code, json.load(error)

    def check(probe_id, observed, expected):
        checks.append({"probe_id": probe_id, "expected": expected, "observed": observed,
                       "passed": observed == expected})

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.01), daemon=True)
    try:
        thread.start()
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect)
        address = "http://127.0.0.1:" + str(server.server_port)
        check("unauthenticated_read_rejected", request()[0], 401)
        check("owner_read_allowed", request("fictional-owner")[0], 200)
        check("cross_tenant_read_rejected", request("fictional-outsider")[0], 403)
        before = request("fictional-owner")[1]["record"]
        check("cross_tenant_write_rejected", request("fictional-outsider", "unauthorized change")[0], 403)
        check("cross_tenant_rejection_preserves_record", request("fictional-owner")[1]["record"], before)
        check("consented_owner_write_allowed", request("fictional-owner", "authorized fictional update")[0], 200)
        check("consented_write_is_observable", request("fictional-owner")[1]["record"]["note"], "authorized fictional update")
        check("consent_revocation_allowed", request("fictional-owner", "revoke", "/consent/revoke")[0], 200)
        check("consent_revocation_is_observable", request("fictional-owner")[1]["consent_active"], False)
        before = request("fictional-owner")[1]["record"]
        check("revoked_consent_write_rejected", request("fictional-owner", "revoked change")[0], 403)
        check("consent_rejection_preserves_record", request("fictional-owner")[1]["record"], before)
        before = request("fictional-owner")[1]["record"]
        check("unauthenticated_write_rejected", request(note="unauthenticated change")[0], 401)
        check("unauthenticated_rejection_preserves_record", request("fictional-owner")[1]["record"], before)
        violations = [check["probe_id"] for check in checks if not check["passed"]]
        return {"case_id": case_id, "checks": checks, "assertions_passed": not violations,
                "checks_passed": len(checks) - len(violations), "checks_total": len(checks),
                "detected_violations": violations}
    finally:
        if thread.is_alive():
            server.shutdown()
        server.server_close()
        if thread.ident is not None:
            thread.join(timeout=5)


def run_rehearsal():
    secure = _run_case("secure_fixture")
    controls = [_run_case("cross_tenant_bypass"), _run_case("consent_bypass")]
    expected = {"cross_tenant_bypass": "cross_tenant_read_rejected",
                "consent_bypass": "revoked_consent_write_rejected"}
    controls_detected = all(expected[control["case_id"]] in control["detected_violations"] for control in controls)
    return {"engine": "fixed fictional tenant-and-consent contract rehearsal",
            "engine_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "mode": "synthetic_data_real_execution", "transport": "real loopback HTTP; proxies disabled",
            "secure_fixture": secure, "negative_controls": controls,
            "both_controls_detected": controls_detected,
            "assertions_passed": secure["assertions_passed"] and controls_detected,
            "limitations": ["Only fixed trusted fictional fixture code is executed; incoming source is never executed",
                            "Negative controls deliberately bypass one boundary each; violations are expected and must be detected",
                            "Not certification of a real application, production isolation, or complete security coverage",
                            "No private application source, real records, credentials, or provider calls are used"]}
