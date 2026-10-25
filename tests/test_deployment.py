import io
import os
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path

from deploy.azure.manage import gemma_update_script, status_script


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.application = self.root / "opt/arkham-creeper"
        self.application.mkdir(parents=True)
        self.package = self.application / "creeper"
        self.package.mkdir()
        (self.package / "__init__.py").write_text("old package\n")
        self.environment = self.root / "environment"
        self.environment.write_text("CREEPER_WEBHOOK_SECRET=unchanged\n")
        self.environment.chmod(0o600)
        self.original_environment = self.environment.read_bytes()
        self.ready = self.root / "gemma-ready"
        self.ready.touch()
        self.bootstrap = self.root / "bootstrap-complete"
        self.bootstrap.touch()
        self.files = {
            "creeper/__init__.py": "new package\n",
            "requirements.txt": "same dependency\n",
            "deploy/creeper-listener.service": "same listener\n",
            "deploy/creeper-worker.service": "same worker\n",
            "LICENSE": "new license\n",
        }
        for relative, content in self.files.items():
            if relative.startswith("creeper/"):
                continue
            path = self.application / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("old license\n" if relative == "LICENSE" else content)
        self.state = self.root / "services"
        self.state.mkdir()
        for service in ["creeper-listener", "creeper-worker", "nginx", "ollama"]:
            (self.state / service).touch()
        self.log = self.root / "commands.log"
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.executable(self.bin / "systemctl", """#!/bin/bash
printf 'systemctl %s\\n' "$*" >> "$FAKE_LOG"
action=$1
shift
if [ "${1:-}" = --quiet ]; then shift; fi
if [ "$action" = is-active ]; then
    for service in "$@"; do
        if [ -f "$FAKE_STATE/$service" ]; then exit 0; fi
    done
    exit 3
fi
for service in "$@"; do
    case "$action" in
        stop) rm -f "$FAKE_STATE/$service" ;;
        start)
            if [ "$service" = creeper-worker ] && [ -f "$FAKE_STATE/fail-restore" ]; then exit 1; fi
            if [ "$service" = creeper-worker ] && [ -f "$FAKE_STATE/fail-start" ]; then
                rm "$FAKE_STATE/fail-start"
                exit 1
            fi
            touch "$FAKE_STATE/$service"
            ;;
        *) exit 99 ;;
    esac
done
""")
        self.executable(self.bin / "curl", """#!/bin/bash
echo curl >> "$FAKE_LOG"
if [ -f "$FAKE_STATE/fail-health" ]; then exit 22; fi
if [ -f "$FAKE_STATE/fail-first-health" ]; then
    rm "$FAKE_STATE/fail-first-health"
    exit 22
fi
printf '{"status":"afloat"}'
""")
        self.executable(self.bin / "sha256sum", "#!/bin/bash\necho archive-sha256\n")
        self.executable(self.bin / "sleep", "#!/bin/bash\nexit 0\n")
        python = self.application / ".venv/bin/python"
        python.parent.mkdir(parents=True)
        self.executable(python, """#!/bin/bash
printf 'python %s\\n' "$*" >> "$FAKE_LOG"
if [ "$1" = -c ] && [ -f "$FAKE_STATE/fail-preflight" ]; then exit 1; fi
exit 0
""")

    def executable(self, path, content):
        path.write_text(content)
        path.chmod(0o755)

    def archive(self):
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
            for relative, content in self.files.items():
                data = content.encode()
                entry = tarfile.TarInfo(relative)
                entry.size = len(data)
                entry.mode = 0o644
                archive.addfile(entry, io.BytesIO(data))
        return buffer.getvalue()

    def execute(self, script):
        script = script.replace("/opt/", str(self.root / "opt") + "/")
        script = script.replace("/etc/arkham-creeper/environment", str(self.environment))
        script = script.replace("/var/lib/ollama/gemma-ready", str(self.ready))
        script = script.replace("/var/lib/arkham-creeper/bootstrap-complete", str(self.bootstrap))
        environment = dict(os.environ, PATH=str(self.bin) + os.pathsep + os.environ["PATH"],
                           FAKE_LOG=str(self.log), FAKE_STATE=str(self.state))
        return subprocess.run(["bash", "-c", script], capture_output=True, text=True, env=environment, timeout=30)

    def commands(self):
        return self.log.read_text() if self.log.exists() else ""

    def assert_original_restored(self):
        self.assertEqual((self.package / "__init__.py").read_text(), "old package\n")
        self.assertEqual((self.application / "LICENSE").read_text(), "old license\n")
        self.assertEqual(self.environment.read_bytes(), self.original_environment)
        self.assertEqual(self.environment.stat().st_mode & 0o777, 0o600)

    def test_status_rejects_one_failed_service_without_health_probe(self):
        (self.state / "creeper-worker").unlink()
        result = self.execute(status_script())
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("curl", self.commands())

    def test_status_requires_bootstrap_marker(self):
        self.bootstrap.unlink()
        result = self.execute(status_script())
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("curl", self.commands())

    def test_status_checks_all_components_before_health(self):
        result = self.execute(status_script())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("nginx active", result.stdout)
        self.assertIn("curl", self.commands())

    def test_update_rejects_dependency_and_service_changes_before_stopping(self):
        for relative in ["requirements.txt", "deploy/creeper-listener.service", "deploy/creeper-worker.service"]:
            with self.subTest(relative=relative):
                original = self.files[relative]
                self.files[relative] = "changed\n"
                result = self.execute(gemma_update_script(self.archive()))
                self.files[relative] = original
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Refusing update", result.stderr)
                self.assertNotIn("systemctl stop", self.commands())
                self.assert_original_restored()
                self.assertFalse(list((self.root / "opt").glob("creeper-update.*")))

    def test_update_preflights_model_before_stopping(self):
        (self.state / "fail-preflight").touch()
        result = self.execute(gemma_update_script(self.archive()))
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("systemctl stop", self.commands())
        self.assert_original_restored()

    def test_update_rejects_different_configured_model_before_stopping(self):
        self.environment.write_text("CREEPER_GEMMA_MODEL=another-model\n")
        result = self.execute(gemma_update_script(self.archive()))
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("systemctl stop", self.commands())
        self.assertEqual(self.environment.read_text(), "CREEPER_GEMMA_MODEL=another-model\n")

    def test_failed_update_restores_package_environment_and_active_services(self):
        (self.state / "fail-start").touch()
        result = self.execute(gemma_update_script(self.archive()))
        self.assertNotEqual(result.returncode, 0)
        self.assert_original_restored()
        self.assertTrue((self.state / "creeper-listener").exists())
        self.assertTrue((self.state / "creeper-worker").exists())
        self.assertFalse(list((self.root / "opt").glob("creeper-update.*")))

    def test_failed_update_preserves_previously_inactive_service(self):
        (self.state / "creeper-worker").unlink()
        (self.state / "fail-start").touch()
        result = self.execute(gemma_update_script(self.archive()))
        self.assertNotEqual(result.returncode, 0)
        self.assert_original_restored()
        self.assertTrue((self.state / "creeper-listener").exists())
        self.assertFalse((self.state / "creeper-worker").exists())

    def test_update_waits_for_listener_startup(self):
        (self.state / "fail-first-health").touch()
        result = self.execute(gemma_update_script(self.archive()))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.commands().splitlines().count("curl"), 2)
        self.assertEqual((self.package / "__init__.py").read_text(), "new package\n")

    def test_failed_startup_health_check_restores_original(self):
        (self.state / "fail-health").touch()
        result = self.execute(gemma_update_script(self.archive()))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("bounded startup health check", result.stderr)
        self.assertEqual(self.commands().splitlines().count("curl"), 20)
        self.assert_original_restored()
        self.assertTrue((self.state / "creeper-listener").exists())
        self.assertTrue((self.state / "creeper-worker").exists())

    def test_failed_restoration_retains_protected_backup(self):
        (self.state / "fail-restore").touch()
        result = self.execute(gemma_update_script(self.archive()))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("restoration needs operator review", result.stderr)
        backups = list((self.root / "opt").glob("creeper-update.*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].stat().st_mode & 0o777, 0o700)
        self.assertEqual((backups[0] / "old-environment").read_bytes(), self.original_environment)
        self.assert_original_restored()

    def test_successful_update_uses_staged_package_and_keeps_secret(self):
        result = self.execute(gemma_update_script(self.archive()))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.package / "__init__.py").read_text(), "new package\n")
        self.assertEqual((self.application / "LICENSE").read_text(), "new license\n")
        self.assertEqual(self.environment.read_text(), self.original_environment.decode() + "CREEPER_GEMMA_MODEL=gemma3:1b\n")
        self.assertEqual(self.package.stat().st_mode & 0o777, 0o755)
        self.assertTrue((self.state / "creeper-listener").exists())
        self.assertTrue((self.state / "creeper-worker").exists())
        self.assertFalse(list((self.root / "opt").glob("creeper-update.*")))


if __name__ == "__main__":
    unittest.main()
