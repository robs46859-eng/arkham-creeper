# Prize categories and executed evidence

## Best Use of Gemma — implemented

The local open-weight Gemma 3 1B model performs contextual code triage and drafts structured review summaries and recommendations. It runs through Ollama on the same isolated CPU server as Cthulhu Daemon, with source-bearing requests confined to loopback. The model cannot execute code, apply patches, or lower configured review signals.

The [challenge criteria](https://dev.to/challenges/hacktoberfest-week3-2026-10-19) allow Gemma running locally or through another hosting provider. The implementation uses Azure compute; no Google-hosted inference API is involved.

Measured fictional-code run on October 25, 2026:

- Four actual Gemma reviews; 18 orchestration/rehearsal assertions passed in the reviewed run at 19:12 UTC.
- 1,073 prompt tokens and 437 generated tokens, measured by the local runtime.
- Review elapsed times: 11.560, 10.583, 14.121, and 20.553 seconds on the small CPU server.
- The model was absent from Ollama’s running-model list after each review following `keep_alive: 0`.
- Model: `gemma3:1b`, Gemma family `gemma3`, quantization `Q4_K_M`.
- Model digest: `97558784bdc9175075a72655bf360b15da17df6b3b9e5182af9f8c0c8e58ba7c`.
- Runtime: Ollama 0.40.11. The validated runtime at `46e09e1` passes 69 focused tests, including renderer regressions and custom-domain deployment guards.
- A separate trusted virtual HTTP fixture passes 13 tenant/consent probes; identical probes detect both deliberately faulty controls. This does not execute incoming code or certify a real application.

[View measured demonstration](https://cthulhu.arkhamprison.com/) · [Machine-readable evidence](https://cthulhu.arkhamprison.com/demo/report.json)

The input scenarios are synthetic and explicitly labeled. These numbers establish execution, not production detection accuracy, verified vulnerabilities, clinical outcomes, or human time saved.

One model error is visible in the reviewed run: Gemma suggests vulnerabilities in the benign fixture's ordinary dictionary `get()` despite no injected execution or SQL sink. The report labels model opinions as unverified and identifies risk claims about that fixture as false positives. The model output is preserved, and no automatic security action follows it.

## GitHub Copilot category — GitHub Actions automation executed

The [challenge’s category description](https://dev.to/challenges/hacktoberfest-week3-2026-10-19) includes automating a project with GitHub Actions. [The workflow](../.github/workflows/ci.yml) runs all 69 tests and the 18-assertion fictional-data demonstration on pushes and pull requests, with read-only repository permissions. [Run 40246949823](https://github.com/robs46859-eng/arkham-creeper/actions/runs/40246949823) passed both steps on [validated runtime `46e09e1`](https://github.com/robs46859-eng/arkham-creeper/tree/46e09e1758fbe3470564d476b7960d9ca1e56046). This entry relies on that stated Actions route; Copilot products were not used. Prize eligibility remains the organizer’s decision.

No other partner category is claimed. See the [final submission](SUBMISSION.md) and [official rules](https://dev.to/page/hacktoberfest-week3-2026-10-19-contest-rules). Repository publication does not publish the DEV article or enter the contest.
