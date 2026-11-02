# Recorded kind development cases — 2026-11-02

Eight real recordings: healthy, incorrect readiness port, incorrect readiness path and unavailable HTTP dependency, for Uvicorn and Go. Evidence and ground-truth labels are separate. These are development cases, not held-out data or independent production validation.

Private pod/client/service IP addresses have been replaced consistently with documentation addresses in 192.0.2.0/24 and 198.51.100.0/24. The bind address 0.0.0.0 and generic lab service dependency are retained because they describe application behavior. Timestamps, ports, routes and evidence IDs are unchanged. No cluster diagnostics are published here.

Source: [GitHub Actions run #2](https://github.com/JeanneBM/aks-readiness-diagnostic-agent/actions/runs/41471820620), commit 0e56f46942d29e45023067c3dc78c82ed081d09b. See eval/2026-11-02-kind/provenance.json for original/published hashes and artifact identity.

Replay from repository root (new output directory required):

```bash
python tools/run_local_lab.py pilot --cases data/recorded-dev/2026-11-02-kind --output .local/runs/recorded-a1-replay --variants A1 --repetitions 3
```

No Docker, Kubernetes cluster or model credentials are needed for replay. The recorded fixture-source hashes describe the source run, not the anonymized evidence. The provenance file identifies the published dataset bytes.
