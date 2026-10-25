# Cthulhu Daemon

A biomimetic code-review Symbiont: a Man o’ War captures repository events, with nutcracker-inspired novelty memory, prairie-dog signal triage, dolphin-inspired model rest, wolf-like provenance, and beaver-like workflow resilience. These are engineering metaphors, not six autonomous agents.

**Code flows in. Evidence surfaces. You keep the final call.**

The passive pipeline floats on repository webhooks, captures signed deliveries, keeps source inert, and digests it later with local open-source AI. See the [six animal-inspired roles and their limits](docs/BIOMIMETIC_DESIGN.md).

## Implemented

- **Sail:** loopback HTTP ingress, exact-byte HMAC-SHA256 verification, repository allowlist, bounded JSON bodies.
- **Tentacles:** replay protection and durable acknowledgement; no executable source files or automatic Git operations.
- **Deep water:** private SQLite payload/source BLOBs, transactional claims, leases, stale-worker fencing, retries, dead letters, backlog limits.
- **Digestion:** read-only retrieval pinned to signed commit SHAs, IsolationForest novelty scoring, configured review rules, and optional local Gemma review with source hashes, model digest, latency, and token counts.
- **Evidence:** actual HTTP, SQLite, and model execution with fictional source and explicit pass/fail checks.
- **Virtual rehearsal:** trusted fictional HTTP tenant/consent contracts, with identical probes against a secure fixture and two deliberately faulty controls. These are separate from captured source and must not be treated as real-application certification.

No verified zero-days, automatic patching, OS sandbox, complete vulnerability detection, or production containment is claimed. IsolationForest is an anomaly detector, not CART. The original prototype’s hardcoded findings and unsupported patch/branch claims have been replaced. Gemma inference is recorded only when explicitly enabled and successfully completed.

## Run locally

Python 3.11+ is required. Install model dependencies once; the synthetic simulation then runs without internet. Live source retrieval requires GitHub network access.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m creeper.simulate
```

The simulation prints its evidence directory. Open `report.html` for measured results and `report.json` for the full record. Each run requires a fresh directory. Evidence is gitignored: private adapters may store private snapshots there.

## Wire a repository

Set `CREEPER_WEBHOOK_SECRET` to a high-entropy secret of at least 32 characters and `CREEPER_REPOSITORIES` to exact comma-separated repository names. Keep secrets in the service environment or secret manager, outside Git. `CREEPER_GITHUB_TOKEN` is optional for public sources; private sources need a narrowly scoped read-only token.

Run separate processes with the same persistent state directory:

```sh
.venv/bin/python -m creeper listen --state .creeper --port 8787
.venv/bin/python -m creeper digest --state .creeper
```

Configure a GitHub webhook at the HTTPS reverse-proxy route `/webhooks/github`, JSON format, with the same secret. Subscribe only to `push` and `pull_request`. Fork PR retrieval requires explicit review. `python nocturnal_agent.py` exposes the same CLI; supply `listen`, `digest`, or `status`.

```sh
.venv/bin/python -m creeper status --state .creeper
.venv/bin/python -m creeper digest --state .creeper --once
```

Acknowledgement proves queue persistence, not scan completion. Failed/partial retrieval produces `analysis_unavailable` and eventually a dead letter. Reports say `no_configured_rule_match`, `novelty_review_required`, or `review_required`; none certifies security. The AI directly routes statistically unusual files for review, even when text rules find nothing.

See [architecture and production boundaries](docs/ARCHITECTURE.md). The stdlib listener requires a production TLS reverse proxy. SQLite needs persistent single-host storage, not ephemeral autoscaling instances.

See [beyond observability](docs/BEYOND_OBSERVABILITY.md) for the distinct assurance direction, its executed negative-control demonstration, and the work still needed before application-specific release gates.

## Public and private stay separate

Keep private adapters, source snapshots, credentials, and evidence outside this public repository. Private installations get separate secrets, repository allowlists, read-only credentials, service identities, and state volumes. The public UI must never receive private code or patient records.

## Local Gemma review

Install a local Ollama runtime and the official `gemma3:1b` model. Its compact open-weight model runs on a small CPU server. Inference is fixed to `127.0.0.1:11434`; environment proxies are disabled for source-bearing requests. No cloud LLM API is used.

```sh
ollama pull gemma3:1b
export CREEPER_GEMMA_MODEL=gemma3:1b
.venv/bin/python -m creeper digest --state .creeper
.venv/bin/python -m creeper.simulate --gemma-model gemma3:1b
```

Gemma reads at most three source excerpts of 1,200 characters each, prioritizing existing review signals. The entire prompt, including metadata, is capped at 2,000 UTF-8 bytes with a 4,096-token context configuration; actual excerpts may be shorter and their lengths are recorded. It drafts a summary and at most three recommendations, records actual tokens and runtime, requests immediate unload, and observes whether the model remains loaded. Model-tag digest changes fail the review rather than silently changing provenance. No model response is executed or applied. Gemma cannot downgrade configured findings. If configured inference fails, the job retries and is not reported as completed. Default simulation without `--gemma-model` still uses IsolationForest only.

Gemma model use is governed separately by [Google’s Gemma terms](https://ai.google.dev/gemma/terms), not this repository’s MIT license. The [official Ollama model listing](https://ollama.com/library/gemma3:1b) identifies the model artifact.

## Hacktoberfest evidence

Week 3’s **Slow and Steady** theme rewards automation using open-source AI. The demonstrated payoff is durable background triage and one review report. No human time savings or automatically repaired threats are inferred.

The [challenge](https://dev.to/challenges/hacktoberfest-week3-2026-10-19) and [official rules](https://dev.to/page/hacktoberfest-week3-2026-10-19-contest-rules) require a DEV post, code, demo, and open-source AI at the core. The deadline is October 25, 2026, 11:59 p.m. PDT (October 26, 12:59 a.m. America/Denver). Work after the deadline must be identified here. This implementation does not submit a post or prize entry.

[Cthulhu Daemon’s measured demonstration](https://cthulhu.arkhamprison.com/) and [machine-readable evidence](https://cthulhu.arkhamprison.com/demo/report.json) show the deployed fictional-data run. The legacy website at https://creeper.arkhamprison.com remains a labeled illustrative simulated console, separate from the deployed listener and worker. A plain IsolationForest run is not evidence for a Gemma prize claim; use a completed Gemma-enabled run with model digest and measured tokens. No other partner integration is implied.

The GitHub repository, Python package, service names, and existing configuration identifiers retain `arkham-creeper` or `creeper` for compatibility; the public project name is Cthulhu Daemon.

## License

MIT for this repository. [scikit-learn](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.IsolationForest.html) supplies the actual local anomaly model under its BSD license. NumPy, SciPy, joblib, and threadpoolctl are installed through its published dependencies. No private application source is included.
