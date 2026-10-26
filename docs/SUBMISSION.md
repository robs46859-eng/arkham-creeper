---
title: "Cthulhu Daemon: I gave background code review tentacles"
published: false
tags: devchallenge, hf26challenge
---

*This is a submission for the [Hacktoberfest Open-Source AI Challenge Week 3: Slow and Steady](https://dev.to/challenges/hacktoberfest-week3-2026-10-19).*

## What I Built

I wanted repository changes to prepare their own first-review context while I did something else—not an agent that silently rewrites production.

**Cthulhu Daemon** is a biomimetic code-assurance Symbiont. It passively catches signed repository events, keeps captured source inert, and turns changes into a bounded review report using local open-source AI.

The Portuguese man o’ war provides the intake metaphor: the **Sail** listens, the **Tentacles** verify and capture, and **Deep Water** holds a durable SQLite queue. Five other animal-inspired responsibilities complete the Symbiont:

- **Clark’s nutcracker:** a reproducible structural-novelty baseline.
- **Prairie dog:** review-signal triage, with uncertainty visible.
- **Dolphin:** model unloading after each review.
- **Wolf:** commit, path, blob, and source-hash provenance.
- **Beaver:** transactions, backpressure, retries, and recoverable work.

These are six engineering inspirations in one pipeline, not six autonomous agents. The developer returns to evidence and review recommendations, rather than repeating intake and source-retrieval chores.

## Demo

[Open Cthulhu Daemon](https://cthulhu.arkhamprison.com/) · [Measured JSON](https://cthulhu.arkhamprison.com/demo/report.json)

![Cthulhu Daemon’s measured report, with dark terminal panels and teal and violet accents](https://raw.githubusercontent.com/robs46859-eng/arkham-creeper/main/docs/assets/cthulhu-daemon-preview.jpg)

The page is a **saved execution report**, not a live interactive scanner. Its four fictional source scenarios exercise actual HTTP signature validation, durable queue transactions, source analysis, and local model inference. The run passes **18 orchestration/rehearsal assertions**. Executable-looking source stays inert; a large benign module receives novelty review without being declared a verified vulnerability.

A separate trusted fictional service exercises **13 tenant-and-consent contract probes**. The secure fixture passes all 13. Identical probes detect **three tenant-boundary violations** and **two consent-boundary violations** in deliberately faulty controls. Those expected failures demonstrate the harness’s sensitivity to planted defects; they do not certify a real application. Captured repository code is never executed by this rehearsal.

Four actual Gemma reviews measured **1,073 prompt tokens and 437 output tokens**, with calls taking approximately **10.6–20.6 seconds** on a small CPU VM. Model unload was observed after every call.

The report also preserves a false positive: Gemma suggests a risk in the benign fixture’s ordinary dictionary `get()`. That unverified opinion remains visible. The demonstration is not an accuracy benchmark or proof of security.

## Code

[GitHub repository](https://github.com/robs46859-eng/arkham-creeper) · [Validated runtime snapshot](https://github.com/robs46859-eng/arkham-creeper/tree/46e09e1758fbe3470564d476b7960d9ca1e56046) · [Passing runtime checks](https://github.com/robs46859-eng/arkham-creeper/actions/runs/40246949823)

The repository includes the [preserved measured record](https://github.com/robs46859-eng/arkham-creeper/blob/main/docs/demo/report.json). The validated runtime passes **69 tests** and the **18-assertion simulation** locally and in GitHub Actions. Later documentation commits do not represent new model measurements.

The repository and package retain `arkham-creeper` and `creeper` identifiers for compatibility; the project’s public name is Cthulhu Daemon.

## How I Built It

A Python listener sits behind an HTTPS reverse proxy. It verifies exact-byte HMAC signatures and the repository allowlist before accepting a delivery. Acknowledgement follows the queue transaction, not merely receipt of an HTTP request. Changed replays are rejected.

A separate worker retrieves source from GitHub at the full commit SHA supplied by the signature-verified event. It checks file/blob identity and treats source as database text, never an import or executable file. Leases and fencing stop stale workers from completing newer claims. Failed work retries and eventually becomes a dead letter rather than a successful scan.

**scikit-learn IsolationForest** supplies structural-novelty scoring. **Gemma 3 1B**, running through local Ollama, explains selected review context. It reads at most three excerpts of 1,200 characters, subject to a stricter **2,000-byte total prompt cap**. Structured output is bounded and has no tool or patch-execution path. Reports retain model digest, source coverage, tokens, timing, and unload state.

Tests cover identity checks, replay protection, claim ownership, prompt limits, truthful rendering, HTTP contracts, and deployment recovery.

The terminal presentation uses embedded Cinzel, JetBrains Mono, and Space Mono fonts. No client-side script or remote font request is needed to inspect the report.

## Why Does Open Innovation Matter?

The runtime model stays in the worker’s controlled environment instead of sending source to a hosted LLM API. I can inspect the orchestration, constrain excerpts, change review rules, and identify the exact model artifact that produced an opinion.

After installing the runtime and weights, inference is local. Live webhook delivery and GitHub retrieval still need a network connection, and hosting still costs money. Private installations require separate credentials, allowlists, queues, and report destinations; the public demo contains fictional data.

The pipeline code is MIT licensed. [Gemma’s separate terms](https://ai.google.dev/gemma/terms), upstream software licenses, and the embedded fonts’ SIL Open Font License remain applicable.

## My Agent Session

I used **Gemini for the initial brainstorming**, exploring how the challenge’s “Slow and Steady” theme could become background review work. I asked about wolf-like traceability, beaver resilience, prairie-dog triage, and nutcracker memory, then added dolphin attention and a man o’ war intake layer.

These selected excerpts show that design conversation—not implementation results.

**My prompt about the animal processes (excerpt):**

> integrate a dynamic scent trail similar to wolves, self-healing like a beaver dam, filter like a prairie dog system, and spatial Intel like a clarks nutcracker

**My follow-up about orchestration:**

> Create an addition to the submission that adds an orchestration similar to how the man ‘o war operates

**Gemini identifying a gap in the early mock-loop design (excerpt):**

> there was no actual external routing happening.

That diagnosis mattered: a proposed gateway is not a verified integration. The conversation supplied the design brief, not proof of successful scans, quarantines, or patches. The delivered Symbiont deliberately narrows the ambitious brainstorm to signed durable intake, commit-bound provenance, bounded advisory analysis, and observed model unloading. Automatic repair, guaranteed vulnerability detection, and eliminated false positives are not delivered claims.

I then used **OpenAI Codex** for implementation, testing, deployment, and this write-up. Gemini and Codex were development assistants; the product’s runtime AI is **scikit-learn and local Gemma**. The public source, tests, and measured fictional-data record establish what ran. Only these selected conversation excerpts are shared; the complete transcript remains private.

## The Lazy Payoff

I wired this workflow to the project’s own repository pushes. Intake, duplicate handling, source retrieval, and review preparation happen in the background without manually launching each scan.

The payoff is a repeatable handoff: leave the pipeline floating, then inspect its report. I measured pipeline execution, not human productivity, so I am not claiming hours saved. Human review remains the final decision. No automatic repairs, verified zero-days, or operating-system execution sandbox is claimed.

## Prize Categories

- **Best Use of Gemma:** local Gemma 3 1B meaningfully produces the measured review summaries and recommendations.
- **Best Use of GitHub Copilot — GitHub Actions automation path:** the [category description](https://dev.to/challenges/hacktoberfest-week3-2026-10-19) includes project automation with GitHub Actions. The [workflow](https://github.com/robs46859-eng/arkham-creeper/blob/main/.github/workflows/ci.yml) runs the tests and simulation on pushes and pull requests with read-only repository permissions. This claim uses that Actions route, not Copilot’s coding agent, CLI, or app.

**Code flows in. Evidence surfaces. You keep the final call.**
