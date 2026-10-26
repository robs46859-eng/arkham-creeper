# Cthulhu Daemon
## A biomimetic code-assurance Symbiont

**Code flows in. Evidence surfaces. You keep the final call.**

Cthulhu Daemon moves repetitive repository-review preparation into the background without giving an AI model authority to execute incoming code or change production. It captures signed webhooks, durably stores inert payloads, retrieves source at exact commit SHAs, and prepares a bounded local AI review for a human decision.

[Measured demonstration](https://cthulhu.arkhamprison.com/) · [Public source](https://github.com/robs46859-eng/arkham-creeper) · [Final submission](SUBMISSION.md)

### How it works

- **Capture:** the Sail and Tentacles verify the raw webhook signature, repository, and delivery identity before acknowledging durable storage.
- **Retain:** Deep Water is a persistent SQLite queue with replay protection, leases, retries, backpressure, and dead letters.
- **Review:** a separate worker checks commit/path/blob provenance, scores structural novelty with IsolationForest, and requests advisory Gemma summaries from bounded source excerpts.
- **Inspect:** the report records source hashes, review signals, model identity, tokens, elapsed time, and observed model unload. Captured source is treated as text, never executed.

The six animal-inspired roles—Man o’ War intake, nutcracker memory, prairie-dog triage, dolphin rest, wolf provenance, and beaver resilience—describe responsibilities in one pipeline, not six autonomous agents.

### What the evidence establishes

| Evidence | Measured result |
| --- | --- |
| Automated validation | 69 tests and 18 orchestration/rehearsal assertions pass |
| Source-review demonstration | Four fictional scenarios with actual HTTP, queue, and local model execution |
| Trusted virtual rehearsal | 13 tenant/consent probes pass against a secure fictional service |
| Deliberately faulty controls | The same probes expose three tenant-boundary and two consent-boundary violations |
| Gemma 3 1B inference | 1,073 prompt tokens; 437 output tokens; about 10.6–20.6 seconds per review; unload observed after each call |

The [validated runtime snapshot](https://github.com/robs46859-eng/arkham-creeper/tree/46e09e1758fbe3470564d476b7960d9ca1e56046) and its [passing automation](https://github.com/robs46859-eng/arkham-creeper/actions/runs/40246949823) support these implementation checks. The saved [machine-readable run](demo/report.json) preserves the measured results, including Gemma’s false positive about the benign fixture’s dictionary `get()`.

### Assurance, not automatic authority

The virtual rehearsal executes only a trusted built-in fictional service. It is separate from incoming source review: it does not run a captured change or certify a real application. No verified zero-day discovery, complete security coverage, automatic patching, operating-system sandbox, or measured developer hours saved is claimed.

The public installation contains no private application source, records, or credentials. Any private installation needs separate identities, allowlists, queues, and report destinations. Local inference uses scikit-learn and Gemma through loopback-only Ollama; live webhook delivery and GitHub retrieval still need network access.

### Presentation and licensing

The public report uses Cthulhu Daemon’s dark terminal theme, teal/violet accents, Cinzel headings, and monospaced data. Fonts and their licenses are embedded without remote runtime dependencies. Pipeline code is MIT licensed; model weights, dependencies, and fonts retain their own terms. Repository/package/service identifiers remain unchanged for compatibility.

The practical payoff is dependable background intake and inspectable review evidence—not an AI-generated promise that code is safe.
