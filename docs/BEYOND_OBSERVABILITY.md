# Beyond observability: the code-assurance direction

Highlight describes session replay, error monitoring, logs, and distributed tracing in its [official repository](https://github.com/highlight/highlight). Its website now redirects to LaunchDarkly; the successor's [Vega documentation](https://launchdarkly.com/docs/fed-docs/home/observability/vega) already describes AI investigations and GitHub fixes. Merely adding an LLM summary is not a credible differentiator.

Creeper's narrower direction is **source-inert change intake plus independently observable security-contract rehearsals**. That is a different workflow, not evidence of overall superiority or a replacement for mature production observability.

## What the build actually demonstrates

1. Signature-verified repository events enter durable storage before acknowledgement. Source is retrieved at pinned commits, checked against Git blob identities, and examined without execution.
2. Local open-weight inference provides bounded advice, with model identity, coverage, and runtime metrics. Advice never applies a patch or certifies a vulnerability.
3. A separate trusted fictional HTTP service exercises tenant authorization, consent revocation, and record preservation using virtual identities and records.
4. The same contract probes run against two deliberately faulty controls. A tenant bypass and a consent bypass must be detected; a report that only passes an accommodating toy fixture is insufficient.
5. The evidence contains expected/observed probe results and the trusted rehearsal engine's source hash. Negative-control failures are expected detections, not hidden or misrepresented as secure outcomes.

The rehearsal is integrated into the measured simulation and CI. It is **not** automatically run against captured repository code and does not establish that an incoming change preserves a real application's security contracts. Live webhook reviews and virtual-fixture rehearsals are separate evidence tracks.

## Where the product must go next

For application-specific assurance, add explicit trusted adapters with versioned contract suites, ephemeral authorized test environments, no production records, and tenant-specific evidence destinations. Only then evaluate candidate changes inside a separate execution sandbox and bind results to the precise candidate build. Approval gates, authenticated artifact attestations, semantic tracking across refactors, and controlled repair proposals are further work—not delivered capabilities.

Keep production observability alongside that workflow. No comparative benchmark, session-replay parity, superior detection rate, zero-day discovery, automatic rollback of customer traffic, or autonomous safe remediation is claimed.
