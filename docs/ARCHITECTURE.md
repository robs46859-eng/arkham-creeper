# Man o’ War orchestration

```mermaid
flowchart LR
    GH[Allowlisted repository webhook] --> TLS[TLS reverse proxy with request limits]
    TLS --> Sail[Loopback Sail: HMAC and body limits]
    Sail --> Tentacles[Delivery identity and repository checks]
    Tentacles --> Deep[(Private SQLite: inert payload BLOB)]
    Deep --> Worker[Separate worker: leases and bounded retries]
    Worker --> Fetch[Read-only GitHub API at signed commit SHA]
    Fetch --> Sources[(Private queue: text-only source BLOB)]
    Sources --> AI[Local IsolationForest novelty score]
    Sources --> Rules[Configured static review signals]
    Sources --> Gemma[Optional local Gemma: bounded excerpts]
    AI --> Report[Review report]
    Rules --> Report
    Gemma --> Report
```

The listener acknowledges only after a SQLite transaction commits. It performs no source retrieval, model loading, shell invocation, branch changes, or imports from payloads. Repeated delivery IDs with the same body and event are idempotent; changed replays get HTTP 409.

GitHub push webhooks describe changes; complete file contents must be fetched separately. The worker uses a fixed GitHub API origin, signed repository names, and full commit SHAs. Payload URLs and inline source fields are ignored. New branches use bounded tree listings. Fork PRs, nonlinear comparisons, possible comparison truncation, binary/oversized files, and traversal paths fail closed for review.

Deep-water memory is a private SQLite database. Source is stored in BLOBs and examined as strings. No source is imported, evaluated, made executable, patched, committed, or run. Removing execution from the pipeline is stronger than merely removing file executable bits, which would not stop an interpreter. A data queue is not an operating-system sandbox.

Each claim has a lease token. Expired jobs can be reclaimed; stale workers cannot overwrite a newer claim. Errors get exponential retries and dead-letter after three claims. Lease expiry may cause duplicate read-only analysis; exactly-once model execution is not claimed.

The local open-source AI is scikit-learn IsolationForest, trained on a reproducible synthetic benign corpus. Every report includes model version, seed, and training fingerprint. Novelty scores are advisory. Three separate configured text rules identify SQL interpolation, shell execution, and dynamic evaluation for review. Neither a score nor a pattern match verifies a zero-day. The old prototype’s hardcoded verified findings and patch-applied claims have been removed.

When explicitly configured, a local Gemma model adds contextual review summaries and recommendations. It receives bounded excerpts over loopback with proxies disabled, has no tools or execution path, cannot lower existing rule dispositions, and records the actual model digest, token usage, elapsed time, excerpt coverage, and observed unload state. Malformed or unavailable inference fails the job for retry instead of silently claiming a completed model review.

## Separate private applications

Private adapters live in a separate repository or private operations folder. Use distinct webhook secrets, read-only GitHub credentials, repository allowlists, state volumes, and service users for public and private code. Do not share queues across these boundaries. Private reports never automatically flow to the public dashboard.

A private adapter can run the actual application’s test APIs on loopback, feed an explicitly selected read-only source snapshot into its own private queue, and compare authorization and consent behavior before and after digestion. Production identity, databases, patient information, and provider calls remain outside the simulation.

## Hosting boundary

The Python listener binds to 127.0.0.1 and needs a supported HTTPS reverse proxy with request/connection limits and timeouts. Run listener and worker as unprivileged services with private state. SQLite requires one host and persistent local storage; it is unsuitable for ephemeral autoscaling instances or a network filesystem. Multi-host deployment needs a shared transactional queue implementation.

Expose only `/webhooks/github` and minimal `/healthz`. Health means the listener responds, not that GitHub retrieval or the worker is ready. Monitor pending/dead jobs and disk usage privately. HTTP 503 signals backpressure; GitHub failed-delivery redelivery must be handled operationally. Add a retention policy for completed private snapshots before production use.

The existing public UI remains a labeled simulated display until an authenticated, redacted report integration is deployed. No private source is sent to it.
