import argparse
import ipaddress
import json
import socket
from pathlib import Path

try:
    from .manage import command, run_script
except ImportError:
    from manage import command, run_script


DOMAIN = "cthulhu.arkhamprison.com"
RESOURCE_GROUP = "rg-arkham-creeper-hf26"
CONFIGURATION = "/etc/nginx/sites-available/cthulhu-daemon"
ENABLED = "/etc/nginx/sites-enabled/cthulhu-daemon"
OWNERSHIP = CONFIGURATION + ".managed"
HASH_CONFIGURATION = "/etc/nginx/conf.d/cthulhu-server-names.conf"
HASH_OWNERSHIP = HASH_CONFIGURATION + ".managed"
ROOT_REDIRECT = "    location = / { return 302 /demo/report.html; }\n"
LEGACY_ROOT_BLOCK = """    location = / {
        alias /var/www/creeper-demo/report.html;
        default_type text/html;
        add_header X-Content-Type-Options nosniff always;
        add_header Cache-Control no-store always;
        add_header Content-Security-Policy "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'" always;
    }
"""


def nginx_configuration():
    return """server {
    listen 80;
    server_name cthulhu.arkhamprison.com;
    client_max_body_size 1m;
    client_body_timeout 10s;
    server_tokens off;
    location = / { return 302 /demo/report.html; }
    location = /report.json { return 302 /demo/report.json; }
    include /etc/nginx/snippets/creeper-demo.conf;
    location = /healthz { proxy_pass http://127.0.0.1:8787; }
    location = /webhooks/github {
        limit_req zone=creeper_ingress burst=20 nodelay;
        proxy_read_timeout 15s;
        proxy_pass http://127.0.0.1:8787;
    }
    location / { return 404; }
}
"""


def guard_script(required=False):
    return """python3 - <<'CTHULHU_GUARD'
import re
from pathlib import Path
domain = 'cthulhu.arkhamprison.com'
configuration = Path('/etc/nginx/sites-available/cthulhu-daemon')
enabled = Path('/etc/nginx/sites-enabled/cthulhu-daemon')
ownership = Path('/etc/nginx/sites-available/cthulhu-daemon.managed')
required = __REQUIRED__
def server_names(path):
    content = re.sub(r'#[^\\n]*', '', path.read_text())
    return {name for declaration in re.findall(r'\\bserver_name\\s+([^;]+);', content) for name in declaration.split()}
if configuration.is_symlink() or ownership.is_symlink():
    raise RuntimeError('Refusing a symlinked domain configuration or ownership record')
if configuration.exists():
    if not ownership.is_file() or ownership.read_text() != domain + '\\n':
        raise RuntimeError('Refusing to overwrite an unmanaged domain configuration')
    if server_names(configuration) != {domain}:
        raise RuntimeError('Refusing a configuration with unexpected server_name values')
elif required or ownership.exists():
    raise RuntimeError('Managed domain configuration is missing')
if enabled.exists() or enabled.is_symlink():
    if not enabled.is_symlink() or enabled.resolve() != configuration.resolve():
        raise RuntimeError('Refusing an unrelated enabled domain configuration')
elif required:
    raise RuntimeError('Managed domain configuration is not enabled')
for directory in ['/etc/nginx/sites-available', '/etc/nginx/sites-enabled']:
    for candidate in Path(directory).iterdir():
        if candidate.resolve() == configuration.resolve() or not candidate.is_file():
            continue
        if domain in server_names(candidate):
            raise RuntimeError('The requested domain is already claimed by another configuration')
CTHULHU_GUARD
""".replace("__REQUIRED__", repr(required))


def transaction_script():
    return """staging=$(mktemp -d /etc/nginx/cthulhu-domain.XXXXXX)
had_configuration=0
had_ownership=0
had_enabled=0
had_hash_configuration=0
had_hash_ownership=0
changed=0
if [ -f /etc/nginx/sites-available/cthulhu-daemon ]; then
    cp -p /etc/nginx/sites-available/cthulhu-daemon "$staging/configuration"
    had_configuration=1
fi
if [ -f /etc/nginx/sites-available/cthulhu-daemon.managed ]; then
    cp -p /etc/nginx/sites-available/cthulhu-daemon.managed "$staging/ownership"
    had_ownership=1
fi
if [ -L /etc/nginx/sites-enabled/cthulhu-daemon ]; then had_enabled=1; fi
if [ -f /etc/nginx/conf.d/cthulhu-server-names.conf ]; then
    cp -p /etc/nginx/conf.d/cthulhu-server-names.conf "$staging/hash-configuration"
    had_hash_configuration=1
fi
if [ -f /etc/nginx/conf.d/cthulhu-server-names.conf.managed ]; then
    cp -p /etc/nginx/conf.d/cthulhu-server-names.conf.managed "$staging/hash-ownership"
    had_hash_ownership=1
fi
finish_domain() {
    outcome=$?
    trap - EXIT
    set +e
    restoration_failed=0
    if [ "$outcome" -ne 0 ] && [ "$changed" -eq 1 ]; then
        if [ "$had_configuration" -eq 1 ]; then
            cp -p "$staging/configuration" /etc/nginx/sites-available/cthulhu-daemon || restoration_failed=1
        else
            rm -f /etc/nginx/sites-available/cthulhu-daemon || restoration_failed=1
        fi
        if [ "$had_ownership" -eq 1 ]; then
            cp -p "$staging/ownership" /etc/nginx/sites-available/cthulhu-daemon.managed || restoration_failed=1
        else
            rm -f /etc/nginx/sites-available/cthulhu-daemon.managed || restoration_failed=1
        fi
        if [ "$had_enabled" -eq 0 ]; then
            rm -f /etc/nginx/sites-enabled/cthulhu-daemon || restoration_failed=1
        fi
        if [ "$had_hash_configuration" -eq 1 ]; then
            cp -p "$staging/hash-configuration" /etc/nginx/conf.d/cthulhu-server-names.conf || restoration_failed=1
        else
            rm -f /etc/nginx/conf.d/cthulhu-server-names.conf || restoration_failed=1
        fi
        if [ "$had_hash_ownership" -eq 1 ]; then
            cp -p "$staging/hash-ownership" /etc/nginx/conf.d/cthulhu-server-names.conf.managed || restoration_failed=1
        else
            rm -f /etc/nginx/conf.d/cthulhu-server-names.conf.managed || restoration_failed=1
        fi
        nginx -t && systemctl reload nginx || restoration_failed=1
    fi
    if [ "$restoration_failed" -eq 0 ]; then
        rm -rf "$staging"
    else
        printf 'Domain rollback needs operator review; protected backup: %s\\n' "$staging" >&2
    fi
    exit "$outcome"
}
trap finish_domain EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
"""


def hash_guard_script():
    return """hash_mode=$(python3 - "$staging/active-nginx.conf" <<'CTHULHU_HASH_GUARD'
import re
import sys
from pathlib import Path
configuration = Path('/etc/nginx/conf.d/cthulhu-server-names.conf')
ownership = Path('/etc/nginx/conf.d/cthulhu-server-names.conf.managed')
content = re.sub(r'#[^\\n]*', '', Path(sys.argv[1]).read_text())
directives = re.findall(r'\\bserver_names_hash_bucket_size\\s+([^;]+);', content)
if configuration.is_symlink() or ownership.is_symlink():
    raise RuntimeError('Refusing a symlinked server-name hash configuration or ownership record')
if configuration.exists():
    if not ownership.is_file() or ownership.read_text() != 'cthulhu.arkhamprison.com\\n':
        raise RuntimeError('Refusing an unmanaged server-name hash configuration')
    if configuration.read_text() != 'server_names_hash_bucket_size 128;\\n' or directives != ['128']:
        raise RuntimeError('Unexpected managed server-name hash configuration or conflicting directive')
    print('preserve')
elif ownership.exists():
    raise RuntimeError('Managed server-name hash configuration is missing')
elif directives:
    raise RuntimeError('Existing explicit server-name hash directive needs operator review; no override attempted')
else:
    print('create')
CTHULHU_HASH_GUARD
)
"""


def root_upgrade_script():
    return """python3 - "$staging/candidate" <<'CTHULHU_ROOT_UPGRADE'
import sys
from pathlib import Path
configuration = Path('/etc/nginx/sites-available/cthulhu-daemon')
content = configuration.read_text()
legacy = __LEGACY_ROOT__
redirect = __ROOT_REDIRECT__
if content.count(legacy) == 1:
    content = content.replace(legacy, redirect, 1)
elif legacy in content or content.count(redirect) != 1:
    raise RuntimeError('Refusing an unexpected managed root route')
Path(sys.argv[1]).write_text(content)
CTHULHU_ROOT_UPGRADE
""".replace("__LEGACY_ROOT__", repr(LEGACY_ROOT_BLOCK)).replace("__ROOT_REDIRECT__", repr(ROOT_REDIRECT))


def prepare_script():
    return """set -euo pipefail
umask 077
test -f /var/www/creeper-demo/report.html
test -f /var/www/creeper-demo/report.json
test -f /etc/nginx/snippets/creeper-demo.conf
nginx -t
""" + guard_script() + transaction_script() + """nginx -T > "$staging/active-nginx.conf" 2> "$staging/active-nginx.stderr"
""" + hash_guard_script() + """if [ "$hash_mode" = create ]; then
    changed=1
    printf 'server_names_hash_bucket_size 128;\\n' > "$staging/hash-candidate"
    install -m 644 "$staging/hash-candidate" /etc/nginx/conf.d/cthulhu-server-names.conf
    printf 'cthulhu.arkhamprison.com\\n' > /etc/nginx/conf.d/cthulhu-server-names.conf.managed
fi
if [ "$had_configuration" -eq 0 ]; then
    cat > "$staging/candidate" <<'CTHULHU_NGINX'
""" + nginx_configuration() + """CTHULHU_NGINX
    cat > "$staging/nginx.conf" <<CTHULHU_TEST
events {}
http {
    server_names_hash_bucket_size 128;
    limit_req_zone \\$binary_remote_addr zone=creeper_ingress:10m rate=5r/s;
    include $staging/candidate;
}
CTHULHU_TEST
    nginx -t -c "$staging/nginx.conf"
    changed=1
    install -m 644 "$staging/candidate" /etc/nginx/sites-available/cthulhu-daemon
    printf 'cthulhu.arkhamprison.com\\n' > /etc/nginx/sites-available/cthulhu-daemon.managed
else
""" + root_upgrade_script() + """    if ! cmp -s "$staging/candidate" /etc/nginx/sites-available/cthulhu-daemon; then
        changed=1
        install -m 644 "$staging/candidate" /etc/nginx/sites-available/cthulhu-daemon
    fi
fi
if [ "$had_enabled" -eq 0 ]; then
    changed=1
    ln -s /etc/nginx/sites-available/cthulhu-daemon /etc/nginx/sites-enabled/cthulhu-daemon
fi
nginx -t
systemctl reload nginx
for service in nginx creeper-listener creeper-worker; do
    systemctl is-active --quiet "$service"
done
healthy=0
for attempt in $(seq 1 20); do
    if curl --fail --silent --show-error --noproxy '*' --max-time 2 --resolve cthulhu.arkhamprison.com:80:127.0.0.1 http://cthulhu.arkhamprison.com/healthz; then
        healthy=1
        break
    fi
    sleep 0.5
done
if [ "$healthy" -ne 1 ]; then
    echo 'New virtual host failed its bounded post-reload health check.' >&2
    exit 1
fi
printf '\\ncthulhu.arkhamprison.com HTTP virtual host prepared; existing Azure host preserved\\n'
"""


def verification_script():
    return """verified_report() {
    local response
    response=$(curl --fail --silent --show-error --location --max-redirs 3 --proto '=https' --proto-redir '=https' --noproxy '*' --max-time 2 --resolve cthulhu.arkhamprison.com:443:127.0.0.1 -w '\\n%{http_code}' "$1") || return 1
    [ "${response##*$'\\n'}" = 200 ] || return 1
    printf '%s\\n' "$response" | grep -F '<h1>Cthulhu Daemon</h1>' > /dev/null
}
verified=0
for attempt in $(seq 1 20); do
    http_code=$(curl --silent --show-error --noproxy '*' --max-time 2 --resolve cthulhu.arkhamprison.com:80:127.0.0.1 -o /dev/null -w '%{http_code}' http://cthulhu.arkhamprison.com/ || true)
    case "$http_code" in
        301|302|307|308)
            if verified_report https://cthulhu.arkhamprison.com/ &&
               verified_report https://cthulhu.arkhamprison.com/demo/report.html &&
               json_code=$(curl --fail --silent --show-error --location --max-redirs 3 --proto '=https' --proto-redir '=https' --noproxy '*' --max-time 2 --resolve cthulhu.arkhamprison.com:443:127.0.0.1 -o /dev/null -w '%{http_code}' https://cthulhu.arkhamprison.com/demo/report.json) &&
               [ "$json_code" = 200 ] &&
               curl --fail --silent --show-error --noproxy '*' --max-time 2 --resolve cthulhu.arkhamprison.com:443:127.0.0.1 https://cthulhu.arkhamprison.com/healthz | grep -E '"status"[[:space:]]*:[[:space:]]*"afloat"' > /dev/null; then
                verified=1
                break
            fi
            ;;
    esac
    sleep 0.5
done
if [ "$verified" -ne 1 ]; then
    echo 'Custom-domain HTTPS routes failed bounded post-reload verification.' >&2
    exit 1
fi
printf 'HTTP redirect, HTTPS landing/report content, JSON evidence, and listener health verified\\n'
"""


def status_script():
    return """set -euo pipefail
nginx -t
""" + guard_script(required=True) + """for service in nginx creeper-listener creeper-worker; do
    systemctl is-active --quiet "$service"
    printf '%s active\\n' "$service"
done
certificate=/etc/letsencrypt/live/cthulhu.arkhamprison.com/fullchain.pem
test -f "$certificate"
openssl x509 -in "$certificate" -noout -checkhost cthulhu.arkhamprison.com
openssl x509 -in "$certificate" -noout -checkend 0
""" + verification_script()


def https_script():
    return """set -euo pipefail
umask 077
nginx -t
""" + guard_script(required=True) + transaction_script() + """changed=1
certbot --nginx --non-interactive --agree-tos --register-unsafely-without-email --redirect --cert-name cthulhu.arkhamprison.com -d cthulhu.arkhamprison.com
nginx -t
systemctl reload nginx
""" + status_script()


def verify_dns(subscription):
    address = command(["az", "network", "public-ip", "show", "--subscription", subscription,
                       "--resource-group", RESOURCE_GROUP, "--name", "creeper-ip", "--query", "ipAddress",
                       "--only-show-errors", "-o", "json"])
    parsed = ipaddress.ip_address(address)
    if parsed.version != 4 or not parsed.is_global:
        raise RuntimeError("The scoped server has no valid public IPv4 address")
    try:
        resolved = sorted(set(socket.gethostbyname_ex(DOMAIN)[2]))
    except OSError as error:
        raise RuntimeError("The requested domain does not resolve; no server changes made") from error
    if resolved != [str(parsed)]:
        raise RuntimeError("Domain DNS does not exclusively match the scoped server; no server changes made")
    return {"public_ip": str(parsed), "resolved_ipv4": resolved}


def execute(action, subscription, work):
    scripts = {"prepare": prepare_script, "enable-https": https_script, "status": status_script}
    if action not in scripts:
        raise ValueError("Unsupported domain action")
    dns = verify_dns(subscription) if action in {"enable-https", "status"} else None
    observed = run_script(subscription, scripts[action]())
    receipt = {"domain": DOMAIN, "action": action, "dns": dns, "observed": observed}
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True, mode=0o700)
    receipt_path = work / ("domain-" + action + "-receipt.json")
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    receipt_path.chmod(0o600)
    return receipt


def main():
    parser = argparse.ArgumentParser(description="Manage only the isolated Cthulhu Daemon custom domain")
    parser.add_argument("action", choices=["prepare", "enable-https", "status"])
    parser.add_argument("--subscription", required=True)
    parser.add_argument("--work", required=True)
    arguments = parser.parse_args()
    print(json.dumps(execute(arguments.action, arguments.subscription, arguments.work), indent=2))


if __name__ == "__main__":
    main()
