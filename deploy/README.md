# Single-host service wiring

These Linux systemd units are used by the Azure deployment helpers in `azure/` and have been exercised on an isolated CPU VM. For another installation, provision a dedicated unprivileged `creeper` user, install the reviewed source and virtual environment at `/opt/arkham-creeper`, and place a root-owned environment file readable only by the service at `/etc/arkham-creeper/environment`. Configure repository allowlists and a new webhook secret there. Add a read-only GitHub token only when needed.

Install both units; they share `/var/lib/arkham-creeper` on a persistent local volume. Put a supported TLS reverse proxy in front of `127.0.0.1:8787`, with a 1 MiB request cap, request timeout, connection/rate limits, and no request-body or signature logging. Proxy only `/webhooks/github` and `/healthz`; keep operational reports private. The public demo separately allowlists the saved fictional report HTML/JSON. Never serve queue databases, source snapshots, environment files, or the model endpoint. Domain, TLS, host firewall, webhook registration, disk retention, private alerts, failed-delivery redelivery, and service startup verification remain deployment tasks.

The listener and worker require a single persistent host; ephemeral autoscaling or multi-host deployment needs a replacement shared transactional queue. Public and private applications require separate installations and state. Do not combine credentials, repository allowlists, or private report feeds.

Acceptance requires a real GitHub ping, an authorized test change, a matching delivery ID in the durable queue, a completed SHA-pinned report, replay verification, and a failed-analysis exercise. A green `/healthz` or a simulated dashboard does not establish these outcomes.
