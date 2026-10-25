import hashlib
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from creeper import rehearse


class ContractRehearsalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.evidence = rehearse.run_rehearsal()

    def test_secure_fixture_passes_real_contract_probes(self):
        secure = self.evidence["secure_fixture"]
        self.assertTrue(secure["assertions_passed"])
        self.assertEqual(secure["checks_passed"], secure["checks_total"])
        self.assertEqual(secure["detected_violations"], [])
        self.assertGreaterEqual(secure["checks_total"], 10)

    def test_same_probes_detect_both_deliberate_bypasses(self):
        self.assertTrue(self.evidence["both_controls_detected"])
        controls = {control["case_id"]: control for control in self.evidence["negative_controls"]}
        secure_ids = [check["probe_id"] for check in self.evidence["secure_fixture"]["checks"]]
        for control in controls.values():
            self.assertEqual([check["probe_id"] for check in control["checks"]], secure_ids)
            self.assertFalse(control["assertions_passed"])
        self.assertIn("cross_tenant_read_rejected", controls["cross_tenant_bypass"]["detected_violations"])
        self.assertIn("cross_tenant_rejection_preserves_record", controls["cross_tenant_bypass"]["detected_violations"])
        self.assertIn("revoked_consent_write_rejected", controls["consent_bypass"]["detected_violations"])
        self.assertIn("consent_rejection_preserves_record", controls["consent_bypass"]["detected_violations"])
        self.assertEqual(set(controls["cross_tenant_bypass"]["detected_violations"]), {
            "cross_tenant_read_rejected", "cross_tenant_write_rejected", "cross_tenant_rejection_preserves_record"})
        self.assertEqual(set(controls["consent_bypass"]["detected_violations"]), {
            "revoked_consent_write_rejected", "consent_rejection_preserves_record"})

    def test_evidence_is_serializable_and_identifies_its_engine(self):
        json.dumps(self.evidence)
        self.assertTrue(self.evidence["assertions_passed"])
        self.assertEqual(self.evidence["engine_source_sha256"], hashlib.sha256(Path(rehearse.__file__).read_bytes()).hexdigest())
        self.assertIn("incoming source is never executed", self.evidence["limitations"][0])

    def test_listener_binds_only_to_loopback_and_closes(self):
        servers = []
        original = rehearse.ThreadingHTTPServer
        def create(address, handler):
            self.assertEqual(address, ("127.0.0.1", 0))
            server = original(address, handler)
            servers.append(server)
            return server
        with patch.object(rehearse, "ThreadingHTTPServer", side_effect=create):
            rehearse._run_case("secure_fixture")
        self.assertEqual(servers[0].socket.fileno(), -1)

    def test_listener_closes_when_probe_raises(self):
        servers = []
        original = rehearse.ThreadingHTTPServer
        def create(address, handler):
            server = original(address, handler)
            servers.append(server)
            return server
        with patch.object(rehearse, "ThreadingHTTPServer", side_effect=create), patch.object(rehearse.urllib.request, "build_opener", side_effect=RuntimeError("fixture failure")):
            with self.assertRaises(RuntimeError):
                rehearse._run_case("secure_fixture")
        self.assertEqual(servers[0].socket.fileno(), -1)


if __name__ == "__main__":
    unittest.main()
