#!/bin/bash
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq zstd curl
curl --fail --location --retry 3 --silent --show-error https://github.com/ollama/ollama/releases/download/v0.40.11/ollama-linux-amd64.tar.zst --output /opt/ollama-linux-amd64.tar.zst
sha256sum /opt/ollama-linux-amd64.tar.zst > /opt/ollama-runtime-sha256.txt
tar --zstd -xf /opt/ollama-linux-amd64.tar.zst -C /usr
id ollama >/dev/null 2>&1 || useradd --system --home /var/lib/ollama --shell /usr/sbin/nologin ollama
cat > /etc/systemd/system/ollama.service <<'UNIT'
[Unit]
Description=Local Gemma inference for Arkham Creeper
After=network-online.target
Wants=network-online.target

[Service]
User=ollama
Group=ollama
StateDirectory=ollama
StateDirectoryMode=0700
WorkingDirectory=/var/lib/ollama
Environment=HOME=/var/lib/ollama
Environment=OLLAMA_HOST=127.0.0.1:11434
Environment=OLLAMA_MODELS=/var/lib/ollama/models
Environment=OLLAMA_NUM_PARALLEL=1
Environment=OLLAMA_MAX_LOADED_MODELS=1
Environment=OLLAMA_NO_CLOUD=1
ExecStart=/usr/bin/ollama serve
Restart=on-failure
RestartSec=5
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
PrivateDevices=yes
MemoryMax=2G
TasksMax=128

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now ollama
for attempt in $(seq 1 30); do
    if curl --fail --silent http://127.0.0.1:11434/api/version > /var/lib/ollama/runtime-version.json; then break; fi
    sleep 1
done
curl --fail --silent --show-error -H 'Content-Type: application/json' -d '{"model":"gemma3:1b","stream":false}' http://127.0.0.1:11434/api/pull > /var/lib/ollama/model-pull.json
python3 -c 'import json; assert json.load(open("/var/lib/ollama/model-pull.json"))["status"] == "success"'
curl --fail --silent http://127.0.0.1:11434/api/tags
touch /var/lib/ollama/gemma-ready
