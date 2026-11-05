# Run the development pilot on GitHub Actions

No local Docker, kind or Azure setup is required.

1. Open Actions → Readiness kind pilot → Run workflow.
2. Select main and confirm Run workflow.
3. Open the run and download the readiness-kind-a1 artifact when finished.

The workflow creates a dedicated kind cluster on an Ubuntu runner, records healthy, port, path and dependency cases for both Uvicorn and Go, then replays A1 three times per case (8 cases, 24 attempts). It makes no model requests and creates no Azure resources. Normal GitHub Actions usage rules apply.

The artifact contains recordings, separate labels, per-attempt results, consistency.json, summary.json, summary.md, source commit/tool versions and cluster diagnostics. Artifacts are retained for 14 days; download evidence you want to preserve. Partial recordings and diagnostic logs are retained on failure where available. Cleanup always attempts to delete the dedicated runner cluster.

The validation step requires a complete eight-case recording, 24 correct A1 attempts, zero errors and no unsupported conclusions. A failed check leaves the actual results visible; it does not rewrite labels or expected results. These are development cases, not held-out validation or evidence of LLM superiority. C1/H are not run by this workflow.

Status: [run #2](https://github.com/JeanneBM/aks-readiness-diagnostic-agent/actions/runs/41471820620) completed successfully on 2 November 2026: eight recorded cases and 24/24 correct A1 attempts, with zero errors and no model calls. Anonymized recordings are preserved under data/recorded-dev/2026-11-02-kind, with provenance and results under eval/2026-11-02-kind. C1/H remain pending. See local-lab.md for recorder details.
