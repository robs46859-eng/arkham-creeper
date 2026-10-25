import argparse
import base64
import hashlib
import json
import subprocess
import zlib
from pathlib import Path


def command(arguments, payload=None):
    result = subprocess.run(arguments, input=json.dumps(payload) if payload is not None else None,
                            capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stderr.strip()[:3000])
    return json.loads(result.stdout) if result.stdout.strip() else None


def run_script(subscription, script):
    wrapped = "bash <<'CREEPER_MANAGED_SCRIPT'\n" + script + "\nCREEPER_MANAGED_SCRIPT\ncreeper_exit=$?\nprintf '\\nCREEPER_EXIT=%s\\n' \"$creeper_exit\"\n"
    result = command(["az", "vm", "run-command", "invoke", "--subscription", subscription,
                      "--resource-group", "rg-arkham-creeper-hf26", "--name", "arkham-creeper-01",
                      "--command-id", "RunShellScript", "--scripts", wrapped, "--only-show-errors", "-o", "json"])
    messages = "\n".join(item.get("message", "") for item in result.get("value", []))
    if "[stdout]" not in messages:
        raise RuntimeError("VM command returned no stdout marker")
    stdout = messages.split("[stdout]", 1)[1].split("[stderr]", 1)[0].strip()
    stderr = messages.split("[stderr]", 1)[1].strip() if "[stderr]" in messages else ""
    stdout, marker, exit_code = stdout.rpartition("CREEPER_EXIT=")
    if not marker or exit_code.strip() != "0":
        raise RuntimeError("VM command failed (exit " + (exit_code.strip() if marker else "unknown") + "): " + (stderr or stdout)[-2000:])
    return stdout.strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["status", "connect-webhook", "test-push", "deliveries", "reports", "enable-gemma", "gemma-demo"])
    parser.add_argument("--subscription", required=True)
    parser.add_argument("--work", required=True)
    arguments = parser.parse_args()
    work = Path(arguments.work).resolve()
    work.mkdir(parents=True, exist_ok=True, mode=0o700)
    subscription = arguments.subscription
    endpoint = "repos/robs46859-eng/arkham-creeper/hooks"
    if arguments.action == "status":
        script = "systemctl is-active creeper-listener creeper-worker nginx; test -f /var/lib/arkham-creeper/bootstrap-complete && echo bootstrap-complete; curl --fail --silent http://127.0.0.1:8787/healthz"
        print(run_script(subscription, script))
    elif arguments.action == "reports":
        script = """cd /opt/arkham-creeper
.venv/bin/python - <<'PY'
import base64, json, sqlite3, zlib
database=sqlite3.connect('/var/lib/arkham-creeper/deep-water.sqlite3')
database.row_factory=sqlite3.Row
rows=[dict(row) for row in database.execute('SELECT delivery,event,digest,state,attempts,report,error FROM jobs ORDER BY received DESC LIMIT 3')]
database.close()
print(base64.b64encode(zlib.compress(json.dumps(rows,separators=(',',':')).encode())).decode())
PY"""
        result = json.loads(zlib.decompress(base64.b64decode(run_script(subscription, script))))
        (work / "live-reports.json").write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps([{key: row[key] for key in ["delivery", "event", "state", "attempts", "error"]} for row in result], indent=2))
    elif arguments.action == "gemma-demo":
        script = """set -euo pipefail
cd /opt/arkham-creeper
creeper_demo_dir="/var/lib/arkham-creeper/public-gemma-$(date -u +%Y%m%dT%H%M%SZ)"
.venv/bin/python -m creeper.simulate --gemma-model gemma3:1b --output "$creeper_demo_dir"
install -d -m 755 /var/www/creeper-demo
install -m 644 "$creeper_demo_dir/report.html" /var/www/creeper-demo/report.html
install -m 644 "$creeper_demo_dir/report.json" /var/www/creeper-demo/report.json
cat > /etc/nginx/snippets/creeper-demo.conf <<'NGINX'
location = /demo { return 302 /demo/report.html; }
location = /demo/ { return 302 /demo/report.html; }
location = /demo/report.html {
    alias /var/www/creeper-demo/report.html;
    default_type text/html;
    add_header X-Content-Type-Options nosniff;
    add_header Cache-Control no-store;
    add_header Content-Security-Policy "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'";
}
location = /demo/report.json {
    alias /var/www/creeper-demo/report.json;
    default_type application/json;
    add_header X-Content-Type-Options nosniff;
    add_header Cache-Control no-store;
}
NGINX
python3 - <<'PY'
from pathlib import Path
path=Path('/etc/nginx/sites-available/creeper')
content=path.read_text()
include='    include /etc/nginx/snippets/creeper-demo.conf;'
if include not in content:
    anchor='    location / { return 404; }'
    if content.count(anchor)!=1: raise ValueError('Unexpected proxy configuration')
    path.write_text(content.replace(anchor,include+'\\n'+anchor))
PY
nginx -t
systemctl reload nginx
echo "$creeper_demo_dir"
"""
        observed = run_script(subscription, script)
        (work / "gemma-demo-receipt.json").write_text(json.dumps({"observed": observed}, indent=2) + "\n")
        print(observed)
    elif arguments.action == "enable-gemma":
        from provision import archive_source
        root = Path(__file__).resolve().parents[2]
        source = archive_source(root)
        encoded = base64.b64encode(source).decode()
        script = """set -euo pipefail
test -f /var/lib/ollama/gemma-ready
systemctl stop creeper-worker creeper-listener
printf '%s' '__ARCHIVE__' | base64 --decode > /opt/creeper-update.tar.gz
tar -xzf /opt/creeper-update.tar.gz -C /opt/arkham-creeper
cd /opt/arkham-creeper
.venv/bin/python -c 'from creeper.gemma import GemmaReviewer; reviewer=GemmaReviewer("gemma3:1b"); print(reviewer.model,reviewer.digest)'
if ! grep -q '^CREEPER_GEMMA_MODEL=' /etc/arkham-creeper/environment; then printf 'CREEPER_GEMMA_MODEL=gemma3:1b\\n' >> /etc/arkham-creeper/environment; fi
systemctl start creeper-listener creeper-worker
systemctl is-active creeper-listener creeper-worker ollama
sha256sum /opt/creeper-update.tar.gz
""".replace("__ARCHIVE__", encoded)
        observed = run_script(subscription, script)
        receipt = {"archive_sha256": hashlib.sha256(source).hexdigest(), "observed": observed, "model": "gemma3:1b"}
        (work / "gemma-deploy-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
        print(json.dumps(receipt, indent=2))
    elif arguments.action == "connect-webhook":
        address = command(["az", "network", "public-ip", "show", "--subscription", subscription,
                           "--resource-group", "rg-arkham-creeper-hf26", "--name", "creeper-ip", "--query", "dnsSettings.fqdn", "-o", "json"])
        url = "https://" + address + "/webhooks/github"
        existing = command(["gh", "api", endpoint])
        if any(hook.get("config", {}).get("url") == url for hook in existing):
            raise RuntimeError("Webhook already exists; inspect it rather than replacing its secret")
        script = """python3 - <<'PY'
from pathlib import Path
for line in Path('/etc/arkham-creeper/environment').read_text().splitlines():
    if line.startswith('CREEPER_WEBHOOK_SECRET='):
        print(line.split('=',1)[1])
PY"""
        secret = run_script(subscription, script)
        if len(secret) != 64 or any(character not in "0123456789abcdef" for character in secret):
            raise RuntimeError("Invalid server-generated webhook secret")
        payload = {"name": "web", "active": True, "events": ["push", "pull_request"],
                   "config": {"url": url, "content_type": "json", "insecure_ssl": "0", "secret": secret}}
        result = command(["gh", "api", "--method", "POST", endpoint, "--input", "-"], payload)
        receipt = {"id": result["id"], "url": url, "events": result["events"], "active": result["active"]}
        (work / "webhook-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
        print(json.dumps(receipt, indent=2))
    else:
        receipt = json.loads((work / "webhook-receipt.json").read_text())
        hook_path = endpoint + "/" + str(receipt["id"])
        if arguments.action == "test-push":
            command(["gh", "api", "--method", "POST", hook_path + "/tests"])
            print(json.dumps({"test_push_requested": True, "hook_id": receipt["id"]}))
        else:
            deliveries = command(["gh", "api", hook_path + "/deliveries"])
            summary = [{key: delivery.get(key) for key in ["id", "guid", "event", "status", "status_code", "redelivery", "delivered_at"]} for delivery in deliveries]
            (work / "github-deliveries.json").write_text(json.dumps(summary, indent=2) + "\n")
            print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
