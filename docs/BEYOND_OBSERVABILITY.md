# Beyond observability: the code-assurance direction

Cthulhu Daemon combines **source-inert change intake with independently observable security-contract rehearsals**. It prepares review evidence without granting incoming code execution or patch authority. This complements production observability rather than replacing session replay, errors, logs, or tracing; no comparative superiority is claimed.

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
