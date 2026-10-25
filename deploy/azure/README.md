# Isolated Azure host

`provision.py` prepares an ARM template and public-code-only source archive. Without `--create` it writes a reviewable plan. With `--create` it refuses to replace an existing resource group, creates a dedicated network and VM, installs the listener/worker services, and enables HTTPS. Inbound SSH is not opened. The webhook secret is generated on the VM.

Before provisioning, verify the selected subscription’s credit eligibility, remaining credit, expiry, current regional retail prices, quota, and actual SKU restrictions. The helper does not enforce a credit-only billing cap or shut resources down at credit expiry. It deliberately does not change subscription billing policies.

```sh
python provision.py --subscription <subscription-id> --location <region> \
  --size <eligible-vm-size> --public-key <ssh-public-key-file> --work <private-work-directory>
```

Review the generated template, then use the same arguments with `--create`. The source archive includes only the `creeper` package, dependency requirement file, license, and service units. Private adapters and evidence must stay outside the public checkout.

`manage.py` provides narrowly scoped operations for the dedicated resource group and VM:

- `status`: checks each required service and the completed-bootstrap marker before probing listener health; any failed check fails the operation.
- `connect-webhook`: creates the public repository webhook, forwarding the signing secret directly from the protected server environment to GitHub without printing it.
- `test-push`: asks GitHub to send its real latest-push test event without changing repository code.
- `deliveries`: records only receipt metadata, excluding webhook request signatures and payloads.
- `reports`: retrieves compact completion metadata for the latest three jobs through Azure Run Command, including source provenance, file counts, and model execution metrics. Full file findings and model text remain in the private server database so larger reports do not exceed the command-output limit.
- `enable-gemma`: stages reviewed public source and validates the already-installed local Gemma model before stopping services. This is a package-only update: changed dependency requirements or service units are rejected before stopping, because those need a separate reviewed deployment. A failed update restores the previous package, protected environment, license, and previously active services. If restoration itself fails, the protected backup is retained and its path is reported for operator recovery.
- `gemma-demo`: runs fictional-code scenarios through actual inference and publishes only their report HTML/JSON. Source BLOBs and state databases are not served.

Each operation takes `--subscription` and `--work`. The local work directory contains operational receipts and must not be published as source. `install-gemma.sh` installs the pinned official Ollama runtime and model on the new VM, binds inference to loopback, and limits it to one loaded model. Model terms are separate from the code license.

## Cthulhu Daemon custom domain

`domain.py` manages only `cthulhu.arkhamprison.com` on the existing isolated VM. It does not edit DNS, the original Azure hostname’s virtual host, the legacy illustrative console at `creeper.arkhamprison.com`, or any private application. The public repository, package, and service identifiers retain their existing names for compatibility.

```sh
python domain.py prepare --subscription <subscription-id> --work <private-work-directory>
```

The `prepare` operation adds a separate HTTP virtual host serving the existing measured report at `/`, with the same signed webhook route, bounded ingress, minimal health endpoint, and public demonstration routes. `/report.json` redirects to `/demo/report.json` so the report’s relative evidence link works at the domain root. Everything else returns 404. Candidate and complete Nginx configurations are validated before reload; unrelated or unmanaged domain configurations are rejected, and failed changes restore the previous domain configuration. Repeating preparation preserves a previously configured HTTPS virtual host rather than replacing it with HTTP-only settings.

Where no explicit active server-name hash-bucket directive exists, preparation adds a dedicated owned `/etc/nginx/conf.d/cthulhu-server-names.conf` setting of `128` to accommodate both public hostnames. It refuses unknown existing explicit directives instead of overriding them. This small shared Nginx setting and its ownership record are backed up and restored with the domain configuration if validation or reload fails; existing virtual-host files remain untouched.

After explicitly authorized DNS changes resolve the subdomain to the isolated VM’s current public IPv4 address, directly or through a CNAME to its Azure hostname, run:

```sh
python domain.py enable-https --subscription <subscription-id> --work <private-work-directory>
python domain.py status --subscription <subscription-id> --work <private-work-directory>
```

Before requesting a certificate or changing the VM for HTTPS, the helper queries only the dedicated Azure public-IP resource and requires the domain’s resolved IPv4 set to match it exclusively. It requests a certificate for this exact hostname, enables HTTP-to-HTTPS redirection, and verifies certificate identity/expiry, listener and worker services, and local Host/SNI HTTP/HTTPS routes without disabling TLS verification. A DNS check is not proof of worldwide propagation; verify public HTTPS and the original Azure endpoint separately after changes. Any existing AAAA record must also be reviewed at the DNS provider before certificate issuance. Operational receipts contain no signing secret or private source and remain in the private work directory.

The queue is single-host SQLite on persistent storage. Monitor disk usage, add retention/backups appropriate to the installation, and inspect dead letters privately. Recovered jobs retain their attempt counts; operator recovery should be audited. A monthly Azure budget is cost tracking, not a hard spending limit.
