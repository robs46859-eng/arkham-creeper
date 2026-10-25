# Isolated Azure host

`provision.py` prepares an ARM template and public-code-only source archive. Without `--create` it writes a reviewable plan. With `--create` it refuses to replace an existing resource group, creates a dedicated network and VM, installs the listener/worker services, and enables HTTPS. Inbound SSH is not opened. The webhook secret is generated on the VM.

Before provisioning, verify the selected subscription’s credit eligibility, remaining credit, expiry, current regional retail prices, quota, and actual SKU restrictions. The helper does not enforce a credit-only billing cap or shut resources down at credit expiry. It deliberately does not change subscription billing policies.

```sh
python provision.py --subscription <subscription-id> --location <region> \
  --size <eligible-vm-size> --public-key <ssh-public-key-file> --work <private-work-directory>
```

Review the generated template, then use the same arguments with `--create`. The source archive includes only the `creeper` package, dependency requirement file, license, and service units. Private adapters and evidence must stay outside the public checkout.

`manage.py` provides narrowly scoped operations for the dedicated resource group and VM:

- `status`: service and listener health.
- `connect-webhook`: creates the public repository webhook, forwarding the signing secret directly from the protected server environment to GitHub without printing it.
- `test-push`: asks GitHub to send its real latest-push test event without changing repository code.
- `deliveries`: records only receipt metadata, excluding webhook request signatures and payloads.
- `reports`: retrieves the latest private-on-disk reports through Azure Run Command.
- `enable-gemma`: deploys reviewed public source and enables an already-installed local Gemma model.
- `gemma-demo`: runs fictional-code scenarios through actual inference and publishes only their report HTML/JSON. Source BLOBs and state databases are not served.

Each operation takes `--subscription` and `--work`. The local work directory contains operational receipts and must not be published as source. `install-gemma.sh` installs the pinned official Ollama runtime and model on the new VM, binds inference to loopback, and limits it to one loaded model. Model terms are separate from the code license.

The queue is single-host SQLite on persistent storage. Monitor disk usage, add retention/backups appropriate to the installation, and inspect dead letters privately. Recovered jobs retain their attempt counts; operator recovery should be audited. A monthly Azure budget is cost tracking, not a hard spending limit.
