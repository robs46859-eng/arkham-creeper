# Prize categories and executed evidence

## Best Use of Gemma — implemented

The local open-weight Gemma 3 1B model performs contextual code triage and drafts structured review summaries and recommendations. It runs through Ollama on the same isolated CPU server as Creeper, with source-bearing requests confined to loopback. The model cannot execute code, apply patches, or lower configured review signals.

The [challenge criteria](https://dev.to/challenges/hacktoberfest-week3-2026-10-19) allow Gemma running locally or through another hosting provider. The implementation uses Azure compute; no Google-hosted inference API is involved.

Measured fictional-code run on October 25, 2026:

- Four actual Gemma reviews; 16 orchestration assertions passed.
- 1,072 prompt tokens and 398 generated tokens, measured by the local runtime.
- Review elapsed times: 10.342, 10.986, 12.986, and 19.947 seconds on the small CPU server.
- The model was absent from Ollama’s running-model list after each review following `keep_alive: 0`.
- Model: `gemma3:1b`, Gemma family `gemma3`, quantization `Q4_K_M`.
- Model digest: `97558784bdc9175075a72655bf360b15da17df6b3b9e5182af9f8c0c8e58ba7c`.
- Runtime: Ollama 0.40.11. Eighteen focused tests pass locally.

[View measured demonstration](https://arkham-creeper-hf26-b0760a60.northcentralus.cloudapp.azure.com/demo/report.html) · [Machine-readable evidence](https://arkham-creeper-hf26-b0760a60.northcentralus.cloudapp.azure.com/demo/report.json)

The input scenarios are synthetic and explicitly labeled. These numbers establish execution, not production detection accuracy, verified vulnerabilities, clinical outcomes, or human time saved. The original generation cap truncated some reviews; incomplete output failed safely, the cap and response length instructions were corrected, and a regression test was added before the successful run.

One model error is visible in the run: Gemma describes the benign repeated formatter as potentially vulnerable to injection despite no injected execution or SQL sink. The report labels model opinions as unverified and identifies this as a false positive. The model output is preserved, and no automatic security action follows it.

## GitHub Copilot category — GitHub Actions automation executed

The challenge’s category description includes automating a project with GitHub Actions. `.github/workflows/ci.yml` runs the focused tests and fictional-data demonstration with read-only repository permissions. [Run 40222966656](https://github.com/robs46859-eng/arkham-creeper/actions/runs/40222966656) passed both steps on public commit `9b60f838d6e5bde61018bdcfaf32d0dc8bd14b17`. This provides executed evidence for that automation path, not a guarantee of prize eligibility. Copilot itself was not used in this implementation.

## Additional categories

Sentry Agent Tracing is a sensible later addition if a Sentry project and DSN are available; current local timings are not a Sentry integration. Temporal or Mastra would require real workflow integration, and Atlas or Tiger Data would require an actual storage integration. The current durable queue does not qualify for those categories by resemblance.

Render and DigitalOcean are not used by the Azure deployment. TabPFN, Tinker, Arduino, Auth0, Backboard, Browserbase, ElevenLabs, Entire, SerpApi, Ultramarine, and a claimed Hacktoberfest `.tech` domain are not integrated. No claims are made for them.

Only categories supported by meaningful use and executed evidence should appear in the final entry. The [official rules](https://dev.to/page/hacktoberfest-week3-2026-10-19-contest-rules) allow at most one prize per participant. No DEV post or prize entry has been submitted by these tools.
