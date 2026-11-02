# Recorded development pilot — 2026-11-02

Source run: https://github.com/JeanneBM/aks-readiness-diagnostic-agent/actions/runs/41471820620

Code commit: 0e56f46942d29e45023067c3dc78c82ed081d09b.

| Evaluation | Cases | Attempts | Correct attempts | Errors | Unsupported conclusions | Model calls |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Original runner A1 | 8 | 24 | 24 | 0 | 0 | 0 |
| A1 replay after anonymization | 8 | 24 | 24 | 0 | 0 | 0 |

- original-a1 preserves the actual runner results, timings and original manifest without rewriting historical hashes.
- sanitized-a1 is a fresh offline replay against the published anonymized data, with its own runtime, timings and manifest.
- provenance.json connects the source ZIP, run, code commit and original/published dataset hashes.
- Dataset: data/recorded-dev/2026-11-02-kind. See its README for the replay command.

Only the diagnostic evidence, labels, recording metadata and evaluation outputs are published. Full runner/cluster diagnostics remain outside the repository. Private IPs were consistently replaced by documentation addresses; timestamps, ports, routes, labels and observation IDs were retained. Checks found no credentials, email addresses, UUIDs, private IPs or personal filesystem paths in these published files. This is an inspection of this dataset, not a general guarantee for arbitrary future recordings.

Eight development recordings and three deterministic replays per recording are not 24 independent incidents. No C1/H run, held-out LLM advantage, production AKS validation or automated repair is claimed.
