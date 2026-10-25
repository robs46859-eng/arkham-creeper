import json
import socket
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from deploy.azure import domain


class CustomDomainTests(unittest.TestCase):
    def execute_guard(self, root, required=False):
        script = domain.guard_script(required).replace("/etc/nginx/", str(root) + "/")
        return subprocess.run(["bash", "-c", script], text=True, capture_output=True, timeout=10)

    def domain_files(self, root):
        available = root / "sites-available"
        enabled = root / "sites-enabled"
        available.mkdir()
        enabled.mkdir()
        configuration = available / "cthulhu-daemon"
        ownership = available / "cthulhu-daemon.managed"
        return configuration, ownership, enabled / "cthulhu-daemon"

    def test_nginx_exposes_only_bounded_public_routes(self):
        configuration = domain.nginx_configuration()
        self.assertIn("server_name cthulhu.arkhamprison.com;", configuration)
        self.assertIn("client_max_body_size 1m;", configuration)
        self.assertIn("client_body_timeout 10s;", configuration)
        self.assertIn("limit_req zone=creeper_ingress burst=20 nodelay;", configuration)
        self.assertIn("proxy_read_timeout 15s;", configuration)
        self.assertIn("location = /report.json { return 302 /demo/report.json; }", configuration)
        self.assertIn("include /etc/nginx/snippets/creeper-demo.conf;", configuration)
        self.assertIn("alias /var/www/creeper-demo/report.html;", configuration)
        self.assertIn("add_header X-Content-Type-Options nosniff always;", configuration)
        self.assertIn("add_header Cache-Control no-store always;", configuration)
        self.assertIn("frame-ancestors 'none'; base-uri 'none'", configuration)
        self.assertIn("location / { return 404; }", configuration)
        self.assertNotIn("11434", configuration)
        self.assertNotIn("/var/lib/", configuration)

    def test_prepare_validates_candidate_before_enabling_and_has_scoped_rollback(self):
        script = domain.prepare_script()
        self.assertLess(script.index('nginx -t -c "$staging/nginx.conf"'), script.index("    ln -s "))
        self.assertIn('cp -p /etc/nginx/sites-available/cthulhu-daemon "$staging/configuration"', script)
        self.assertIn('cp -p "$staging/configuration" /etc/nginx/sites-available/cthulhu-daemon', script)
        self.assertIn("Refusing a configuration with unexpected server_name values", script)
        self.assertIn("Refusing to overwrite an unmanaged domain configuration", script)
        self.assertIn("already claimed by another configuration", script)
        self.assertIn("if [ \"$had_configuration\" -eq 0 ]; then", script)
        self.assertNotIn("/etc/nginx/sites-available/creeper\n", script)
        self.assertNotIn("certbot ", script)
        self.assertIn("server_names_hash_bucket_size 128;", script)
        self.assertIn("nginx -T >", script)
        self.assertIn("Existing explicit server-name hash directive needs operator review", script)
        self.assertIn('cp -p "$staging/hash-configuration" /etc/nginx/conf.d/cthulhu-server-names.conf', script)
        self.assertIn('cp -p "$staging/hash-ownership" /etc/nginx/conf.d/cthulhu-server-names.conf.managed', script)

    def test_hash_guard_creates_only_when_no_explicit_directive_and_preserves_owned_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "conf.d").mkdir()
            active = root / "active-nginx.conf"
            active.write_text("http { server { server_name unrelated.example; } }\n")
            script = 'staging="' + temporary + '"\n' + domain.hash_guard_script().replace("/etc/nginx/", temporary + "/") + 'printf "%s" "$hash_mode"\n'
            result = subprocess.run(["bash", "-eu", "-c", script], text=True, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "create")
            configuration = root / "conf.d/cthulhu-server-names.conf"
            ownership = root / "conf.d/cthulhu-server-names.conf.managed"
            configuration.write_text("server_names_hash_bucket_size 128;\n")
            ownership.write_text(domain.DOMAIN + "\n")
            active.write_text("http { server_names_hash_bucket_size 128; }\n")
            result = subprocess.run(["bash", "-eu", "-c", script], text=True, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "preserve")

    def test_hash_guard_refuses_unknown_explicit_directives_or_unmanaged_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "conf.d").mkdir()
            active = root / "active-nginx.conf"
            script = 'staging="' + temporary + '"\n' + domain.hash_guard_script().replace("/etc/nginx/", temporary + "/")
            for value in ["64", "128", "256"]:
                active.write_text("http { server_names_hash_bucket_size " + value + "; }\n")
                result = subprocess.run(["bash", "-eu", "-c", script], text=True, capture_output=True, timeout=10)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("no override attempted", result.stderr)
            active.write_text("http {}\n")
            (root / "conf.d/cthulhu-server-names.conf").write_text("server_names_hash_bucket_size 128;\n")
            result = subprocess.run(["bash", "-eu", "-c", script], text=True, capture_output=True, timeout=10)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unmanaged server-name hash configuration", result.stderr)

    def test_failed_domain_transaction_restores_or_removes_owned_hash_files(self):
        for preexisting in [False, True]:
            with self.subTest(preexisting=preexisting), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                configuration, ownership, enabled = self.domain_files(root)
                (root / "conf.d").mkdir()
                hash_configuration = root / "conf.d/cthulhu-server-names.conf"
                hash_ownership = root / "conf.d/cthulhu-server-names.conf.managed"
                paths = [configuration, ownership, hash_configuration, hash_ownership]
                if preexisting:
                    for path in paths:
                        path.write_text("original " + path.name + "\n")
                    enabled.symlink_to(configuration)
                script = "set -euo pipefail\numask 077\nnginx() { return 0; }\nsystemctl() { return 0; }\n"
                script += domain.transaction_script().replace("/etc/nginx/", temporary + "/")
                script += "changed=1\n"
                for path in paths:
                    script += 'printf "changed\\n" > "' + str(path) + '"\n'
                if not preexisting:
                    script += 'ln -s "' + str(configuration) + '" "' + str(enabled) + '"\n'
                script += "exit 7\n"
                result = subprocess.run(["bash", "-c", script], text=True, capture_output=True, timeout=10)
                self.assertEqual(result.returncode, 7, result.stderr)
                for path in paths:
                    if preexisting:
                        self.assertEqual(path.read_text(), "original " + path.name + "\n")
                    else:
                        self.assertFalse(path.exists())
                self.assertEqual(enabled.is_symlink(), preexisting)
                self.assertFalse(list(root.glob("cthulhu-domain.*")))

    def test_prepare_waits_for_reloaded_vhost_and_rolls_back_persistent_health_failure(self):
        for failed_probes in [1, 20]:
            with self.subTest(failed_probes=failed_probes), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                nginx = root / "nginx"
                nginx.mkdir()
                configuration, ownership, enabled = self.domain_files(nginx)
                (nginx / "conf.d").mkdir()
                (nginx / "snippets").mkdir()
                (nginx / "snippets/creeper-demo.conf").write_text("public routes\n")
                public = root / "public"
                public.mkdir()
                (public / "report.html").write_text("measured report\n")
                (public / "report.json").write_text("{}\n")
                log = root / "curl.log"
                prefix = """curl_count=0
nginx() {
    if [ "${1:-}" = -T ]; then printf 'events {}\\nhttp {}\\n'; fi
    return 0
}
systemctl() { return 0; }
sleep() { return 0; }
curl() {
    curl_count=$((curl_count + 1))
    printf '%s\\n' "$curl_count" >> '__LOG__'
    if [ "$curl_count" -le __FAILED__ ]; then return 22; fi
    printf '{"status":"afloat"}'
    return 0
}
""".replace("__LOG__", str(log)).replace("__FAILED__", str(failed_probes))
                script = prefix + domain.prepare_script().replace("/etc/nginx/", str(nginx) + "/").replace("/var/www/creeper-demo/", str(public) + "/")
                result = subprocess.run(["bash", "-c", script], text=True, capture_output=True, timeout=10)
                if failed_probes == 1:
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(len(log.read_text().splitlines()), 2)
                    self.assertTrue(configuration.is_file())
                    self.assertTrue(ownership.is_file())
                    self.assertTrue(enabled.is_symlink())
                    self.assertTrue((nginx / "conf.d/cthulhu-server-names.conf").is_file())
                else:
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("bounded post-reload health check", result.stderr)
                    self.assertEqual(len(log.read_text().splitlines()), 20)
                    self.assertFalse(configuration.exists())
                    self.assertFalse(ownership.exists())
                    self.assertFalse(enabled.is_symlink())
                    self.assertFalse((nginx / "conf.d/cthulhu-server-names.conf").exists())
                self.assertFalse(list(nginx.glob("cthulhu-domain.*")))

    def test_status_checks_certificate_services_and_local_host_routes(self):
        script = domain.status_script()
        self.assertIn("nginx creeper-listener creeper-worker", script)
        self.assertIn("-checkhost cthulhu.arkhamprison.com", script)
        self.assertIn("-checkend 0", script)
        self.assertIn("--resolve cthulhu.arkhamprison.com:443:127.0.0.1", script)
        self.assertIn("--resolve cthulhu.arkhamprison.com:80:127.0.0.1", script)
        self.assertIn("for route in / /demo/report.json /healthz", script)
        self.assertNotIn("--insecure", script)

    def test_generated_scripts_have_valid_shell_syntax(self):
        for script in [domain.prepare_script(), domain.https_script(), domain.status_script()]:
            result = subprocess.run(["bash", "-n"], input=script, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_guard_refuses_unmanaged_configuration_and_unrelated_server_name(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            configuration, ownership, _enabled = self.domain_files(root)
            configuration.write_text(domain.nginx_configuration())
            result = self.execute_guard(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unmanaged", result.stderr)
            ownership.write_text(domain.DOMAIN + "\n")
            configuration.write_text("server { server_name unrelated.example; }\n")
            result = self.execute_guard(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unexpected server_name", result.stderr)

    def test_guard_accepts_owned_http_and_https_but_rejects_other_domain_claims(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            configuration, ownership, enabled = self.domain_files(root)
            configuration.write_text(domain.nginx_configuration() + "server { listen 443 ssl; server_name " + domain.DOMAIN + "; }\n")
            original = configuration.read_bytes()
            ownership.write_text(domain.DOMAIN + "\n")
            enabled.symlink_to(configuration)
            result = self.execute_guard(root, required=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(configuration.read_bytes(), original)
            (root / "sites-available/unrelated").write_text("server { server_name " + domain.DOMAIN + "; }\n")
            result = self.execute_guard(root, required=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("already claimed", result.stderr)

    def test_guard_rejects_unrelated_enabled_file_and_missing_required_vhost(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _configuration, _ownership, enabled = self.domain_files(root)
            result = self.execute_guard(root, required=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("configuration is missing", result.stderr)
            enabled.write_text("unrelated\n")
            result = self.execute_guard(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unrelated enabled", result.stderr)

    @patch.object(domain, "run_script")
    @patch.object(domain.socket, "gethostbyname_ex", return_value=(domain.DOMAIN, [], ["20.98.41.137"]))
    @patch.object(domain, "command", return_value="20.98.41.137")
    def test_https_verifies_scoped_dns_before_vm_mutation(self, command, lookup, run_script):
        order = []
        command.side_effect = lambda _arguments: order.append("azure-ip") or "20.98.41.137"
        lookup.side_effect = lambda _domain: order.append("dns") or (domain.DOMAIN, [], ["20.98.41.137"])
        run_script.side_effect = lambda *_arguments: order.append("vm") or "verified"
        with tempfile.TemporaryDirectory() as temporary:
            receipt = domain.execute("enable-https", "subscription", temporary)
            path = Path(temporary) / "domain-enable-https-receipt.json"
            self.assertEqual(json.loads(path.read_text()), receipt)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(order, ["azure-ip", "dns", "vm"])
        arguments = command.call_args.args[0]
        self.assertIn(domain.RESOURCE_GROUP, arguments)
        self.assertIn("creeper-ip", arguments)
        self.assertIn("subscription", arguments)
        script = run_script.call_args.args[1]
        self.assertIn("certbot --nginx --non-interactive --agree-tos", script)
        self.assertIn("--cert-name cthulhu.arkhamprison.com -d cthulhu.arkhamprison.com", script)
        self.assertNotIn("cloudapp.azure.com", script)

    @patch.object(domain, "run_script")
    @patch.object(domain.socket, "gethostbyname_ex")
    @patch.object(domain, "command", return_value="20.98.41.137")
    def test_dns_mismatch_or_missing_resolution_never_mutates_vm(self, _command, lookup, run_script):
        with tempfile.TemporaryDirectory() as temporary:
            for addresses in [["203.0.113.8"], ["20.98.41.137", "203.0.113.8"], []]:
                lookup.return_value = (domain.DOMAIN, [], addresses)
                with self.assertRaisesRegex(RuntimeError, "no server changes made"):
                    domain.execute("enable-https", "subscription", temporary)
            lookup.side_effect = socket.gaierror("not found")
            with self.assertRaisesRegex(RuntimeError, "does not resolve"):
                domain.execute("enable-https", "subscription", temporary)
        run_script.assert_not_called()

    @patch.object(domain, "run_script", return_value="prepared")
    @patch.object(domain, "verify_dns")
    def test_prepare_does_not_require_dns_and_cannot_accept_another_domain(self, verify_dns, run_script):
        with tempfile.TemporaryDirectory() as temporary:
            receipt = domain.execute("prepare", "subscription", temporary)
            self.assertEqual(receipt["domain"], "cthulhu.arkhamprison.com")
            self.assertIsNone(receipt["dns"])
            with self.assertRaises(ValueError):
                domain.execute("evil.example; touch /tmp/attack", "subscription", temporary)
        verify_dns.assert_not_called()
        self.assertEqual(run_script.call_count, 1)


if __name__ == "__main__":
    unittest.main()
