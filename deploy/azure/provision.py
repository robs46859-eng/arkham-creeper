import argparse
import base64
import hashlib
import io
import json
import subprocess
import tarfile
from pathlib import Path


def azure(*arguments):
    result = subprocess.run(["az", *arguments, "--only-show-errors", "-o", "json"], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stderr.strip()[:5000])
    return json.loads(result.stdout) if result.stdout.strip() else None


def archive_source(root):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for relative in ["creeper", "requirements.txt", "LICENSE", "deploy/creeper-listener.service", "deploy/creeper-worker.service"]:
            path = root / relative
            if path.is_dir():
                for source in sorted(path.glob("*.py")):
                    archive.add(source, arcname=str(source.relative_to(root)))
            else:
                archive.add(path, arcname=relative)
    return buffer.getvalue()


def bootstrap(source, fqdn):
    script = """#!/bin/bash
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y python3-venv nginx certbot python3-certbot-nginx curl
id creeper >/dev/null 2>&1 || useradd --system --home /var/lib/arkham-creeper --shell /usr/sbin/nologin creeper
install -d -m 755 /opt/arkham-creeper
tar -xzf /opt/creeper-source.tar.gz -C /opt/arkham-creeper
python3 -m venv /opt/arkham-creeper/.venv
/opt/arkham-creeper/.venv/bin/python -m pip install --no-cache-dir -r /opt/arkham-creeper/requirements.txt
install -d -m 700 /etc/arkham-creeper
if [ ! -f /etc/arkham-creeper/environment ]; then
    umask 077
    printf 'CREEPER_REPOSITORIES=robs46859-eng/arkham-creeper\nCREEPER_WEBHOOK_SECRET=' > /etc/arkham-creeper/environment
    openssl rand -hex 32 >> /etc/arkham-creeper/environment
fi
install -m 644 /opt/arkham-creeper/deploy/creeper-listener.service /etc/systemd/system/
install -m 644 /opt/arkham-creeper/deploy/creeper-worker.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now creeper-listener creeper-worker
cat > /etc/nginx/sites-available/creeper <<'NGINX'
limit_req_zone $binary_remote_addr zone=creeper_ingress:10m rate=5r/s;
server {
    listen 80;
    server_name __FQDN__;
    client_max_body_size 1m;
    client_body_timeout 10s;
    server_tokens off;
    location = /healthz { proxy_pass http://127.0.0.1:8787; }
    location = /webhooks/github {
        limit_req zone=creeper_ingress burst=20 nodelay;
        proxy_read_timeout 15s;
        proxy_pass http://127.0.0.1:8787;
    }
    location / { return 404; }
}
NGINX
ln -sf /etc/nginx/sites-available/creeper /etc/nginx/sites-enabled/creeper
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl enable --now nginx
systemctl reload nginx
certbot --nginx --non-interactive --agree-tos --register-unsafely-without-email --redirect -d __FQDN__
curl --fail --silent https://__FQDN__/healthz
touch /var/lib/arkham-creeper/bootstrap-complete
""".replace("__FQDN__", fqdn)
    configuration = {"write_files": [
        {"path": "/opt/creeper-source.tar.gz", "permissions": "0600", "encoding": "b64", "content": base64.b64encode(source).decode()},
        {"path": "/root/creeper-bootstrap.sh", "permissions": "0700", "content": script}],
        "runcmd": [["bash", "/root/creeper-bootstrap.sh"]]}
    return base64.b64encode(("#cloud-config\n" + json.dumps(configuration)).encode()).decode()


def template(location, size, public_key, custom_data, dns_label):
    resources = []
    network_version = "2023-09-01"
    def identifier(resource_type, name):
        return "[resourceId('" + resource_type + "', '" + name + "')]"
    def add(resource_type, name, properties, dependencies=(), api_version=network_version, extra=None):
        resource = {"type": resource_type, "apiVersion": api_version, "name": name, "location": location,
                    "properties": properties, "dependsOn": list(dependencies), "tags": {"project": "arkham-creeper", "funding": "founders-credits", "data": "public-code-only"}}
        if extra:
            resource.update(extra)
        resources.append(resource)
    add("Microsoft.Network/networkSecurityGroups", "creeper-nsg", {"securityRules": [
        {"name": "https", "properties": {"priority": 100, "direction": "Inbound", "access": "Allow", "protocol": "Tcp", "sourcePortRange": "*", "destinationPortRange": "443", "sourceAddressPrefix": "Internet", "destinationAddressPrefix": "*"}},
        {"name": "acme-http", "properties": {"priority": 110, "direction": "Inbound", "access": "Allow", "protocol": "Tcp", "sourcePortRange": "*", "destinationPortRange": "80", "sourceAddressPrefix": "Internet", "destinationAddressPrefix": "*"}}]})
    add("Microsoft.Network/virtualNetworks", "creeper-vnet", {"addressSpace": {"addressPrefixes": ["10.74.0.0/24"]}, "subnets": [{"name": "application", "properties": {"addressPrefix": "10.74.0.0/24", "networkSecurityGroup": {"id": identifier("Microsoft.Network/networkSecurityGroups", "creeper-nsg")}}}]}, [identifier("Microsoft.Network/networkSecurityGroups", "creeper-nsg")])
    add("Microsoft.Network/publicIPAddresses", "creeper-ip", {"publicIPAllocationMethod": "Static", "publicIPAddressVersion": "IPv4", "dnsSettings": {"domainNameLabel": dns_label}}, extra={"sku": {"name": "Standard"}})
    add("Microsoft.Network/networkInterfaces", "creeper-nic", {"ipConfigurations": [{"name": "primary", "properties": {"privateIPAllocationMethod": "Dynamic", "subnet": {"id": "[resourceId('Microsoft.Network/virtualNetworks/subnets', 'creeper-vnet', 'application')]"}, "publicIPAddress": {"id": identifier("Microsoft.Network/publicIPAddresses", "creeper-ip")}}}]}, [identifier("Microsoft.Network/virtualNetworks", "creeper-vnet"), identifier("Microsoft.Network/publicIPAddresses", "creeper-ip")])
    add("Microsoft.Compute/virtualMachines", "arkham-creeper-01", {
        "hardwareProfile": {"vmSize": size},
        "storageProfile": {"imageReference": {"publisher": "Canonical", "offer": "ubuntu-24_04-lts", "sku": "server", "version": "latest"},
                           "osDisk": {"createOption": "FromImage", "diskSizeGB": 32, "managedDisk": {"storageAccountType": "StandardSSD_LRS"}, "deleteOption": "Delete"}},
        "osProfile": {"computerName": "arkham-creeper", "adminUsername": "creeperadmin", "customData": custom_data,
                      "linuxConfiguration": {"disablePasswordAuthentication": True, "provisionVMAgent": True, "ssh": {"publicKeys": [{"path": "/home/creeperadmin/.ssh/authorized_keys", "keyData": public_key}]}}},
        "networkProfile": {"networkInterfaces": [{"id": identifier("Microsoft.Network/networkInterfaces", "creeper-nic"), "properties": {"primary": True, "deleteOption": "Delete"}}]},
        "securityProfile": {"securityType": "TrustedLaunch", "uefiSettings": {"secureBootEnabled": True, "vTpmEnabled": True}},
        "diagnosticsProfile": {"bootDiagnostics": {"enabled": True}}}, [identifier("Microsoft.Network/networkInterfaces", "creeper-nic")], api_version="2024-03-01")
    return {"$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentTemplate.json#", "contentVersion": "1.0.0.0", "resources": resources,
            "outputs": {"fqdn": {"type": "string", "value": "[reference(resourceId('Microsoft.Network/publicIPAddresses', 'creeper-ip')).dnsSettings.fqdn]"}}}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--subscription", required=True)
    parser.add_argument("--location", required=True)
    parser.add_argument("--size", required=True)
    parser.add_argument("--public-key", required=True)
    parser.add_argument("--work", required=True)
    parser.add_argument("--create", action="store_true")
    arguments = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    work = Path(arguments.work).resolve()
    work.mkdir(parents=True, exist_ok=True, mode=0o700)
    work.chmod(0o700)
    group = "rg-arkham-creeper-hf26"
    label = "arkham-creeper-hf26-" + arguments.subscription[:8]
    fqdn = label + "." + arguments.location + ".cloudapp.azure.com"
    source = archive_source(root)
    body = template(arguments.location, arguments.size, Path(arguments.public_key).read_text().strip(), bootstrap(source, fqdn), label)
    template_path = work / "azure-template.json"
    template_path.write_text(json.dumps(body, indent=2))
    print(json.dumps({"subscription": arguments.subscription, "group": group, "region": arguments.location, "size": arguments.size,
                      "fqdn": fqdn, "source_archive_sha256": hashlib.sha256(source).hexdigest(), "template": str(template_path), "create": arguments.create}, indent=2), flush=True)
    if not arguments.create:
        return
    existing = azure("group", "exists", "--subscription", arguments.subscription, "--name", group)
    if existing:
        raise RuntimeError("Refusing to replace an existing resource group")
    azure("group", "create", "--subscription", arguments.subscription, "--name", group, "--location", arguments.location,
          "--tags", "project=arkham-creeper", "funding=founders-credits", "data=public-code-only")
    azure("deployment", "group", "validate", "--subscription", arguments.subscription, "--resource-group", group, "--template-file", str(template_path))
    result = azure("deployment", "group", "create", "--subscription", arguments.subscription, "--resource-group", group,
                   "--name", "creeper-initial", "--template-file", str(template_path))
    receipt = {"deployment_id": result["id"], "state": result["properties"]["provisioningState"], "outputs": result["properties"].get("outputs")}
    (work / "provision-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2), flush=True)


if __name__ == "__main__":
    main()
