# Local development pilot

Goal: record eight development cases from real Uvicorn and Go HTTP applications, then replay A1/C1/H on exactly those bundles. No AKS, ACR or Azure infrastructure is created.

## Prerequisites

- Python 3.11 or newer and the package installed with `python -m pip install -e .`.
- Docker running with Linux-container support.
- kind and kubectl available on PATH.
- A dedicated local kind cluster; the default name is readiness-diag.
- Internet access for the first container-image and package downloads.

Run in the repository root, in Windows Git Bash, PowerShell or a Linux shell:

```bash
python tools/run_local_lab.py check
```

This checks tools and the Docker daemon, without creating resources. It does not install missing software.

## Record the development data

```bash
python tools/run_local_lab.py record --create-cluster --output .local/recordings/dev-001 --allow-local-lab
```

The recorder uses only context kind-readiness-diag and namespace readiness-diag-lab. It checks the namespace ownership label before changing its resources. It never switches your current context. --create-cluster creates that local cluster only if missing; it is not a cloud deployment flag.

It builds and loads the two images, starts a separate HTTP dependency and records these cases for each framework:

| Case | Injection | Independent observation required |
| --- | --- | --- |
| Healthy | None | Pod Ready=True |
| Port | Probe targets 9090 while application listens on 8080 | Connection-refused readiness Event |
| Path | Probe targets an unregistered path | Readiness HTTP 404 Event |
| Dependency | Scale the real dependency Deployment to zero | Readiness HTTP 503 Event |

Application readiness checks actually request the separate dependency over HTTP. Unlike demo/app.py, these apps do not simulate the dependency result with a boolean. Go uses net/http and structured slog output; Uvicorn provides its own server startup output and serves the ASGI application.

The application logs its configured readiness route explicitly. That route message is application-provided evidence, not framework magic or independent proof. The baseline includes known development patterns for both frameworks. Matching these eight cases does not show generalization.

The recorder writes:

- evidence/R001.json through R008.json: bounded, sanitized inputs.
- labels/R001.json through R008.json: separate injection ground truth, framework, scenario and acceptable evidence alternatives.
- recording.json: status, timestamps, image IDs and fixture-source hashes.

Logs are recorded by the collector, not synthesized by the recorder. A label is only written after the expected fault and required evidence are observed. Setup/recording errors remain visible; incomplete recordings are refused by evaluation. Never rename an incomplete recording as a completed dataset.

Cases use new standalone Pods and the dependency is restored before the next case. Successful recording removes case Pods and scales the dependency to zero. The local cluster and namespace remain for inspection. A failed recording may leave resources running; use the cleanup command when finished.

## Inspect and run the baseline

Review the recorded evidence and labels first. Check logs, readiness Events and source support; do not publish raw logs without inspection.

```bash
python tools/run_local_lab.py pilot --cases .local/recordings/dev-001 --output .local/runs/recorded-a1-001 --repetitions 3
```

This makes no model calls. If setup succeeded but A1 cannot diagnose a real development format, inspect the evidence and improve A1 fairly before final freezing. Do not weaken it to create model advantage.

## Optional paid model pilot

Set READINESS_ENDPOINT, READINESS_API_KEY, READINESS_MODEL and READINESS_PROVIDER locally as documented in docs/usage.md. Then:

```bash
python tools/run_local_lab.py pilot --cases .local/recordings/dev-001 --output .local/runs/recorded-paired-001 --variants A1,C1,H --repetitions 3 --allow-model-calls
```

Eight cases and three repetitions mean 24 C1 calls plus up to 24 H calls, not eight calls. H calls the provider only where A1 abstains. There are no automatic retries. No monetary price is assumed; actual charges depend on the deployment and token usage.

Inspect summary.md, summary.json, consistency.json and every erroneous diagnosis. Results are development results. This pilot does not support a held-out superiority claim or enabling remediation.

## Freeze after the pilot

After reviewing and improving both approaches, preserve a development implementation freeze with model configuration:

```bash
python -m readiness_agent.cli freeze --cases .local/recordings/dev-001 --include-model-config --output .local/preregistration-dev.json
```

Do not change the frozen implementation afterward. Independently prepared held-out cohorts later use this manifest while recording their own dataset hashes. See docs/evaluation.md. The eight development cases are never relabeled as held-out.

## Cleanup

Delete only the owned lab namespace:

```bash
python tools/run_local_lab.py cleanup --allow-local-lab
```

To delete the entire dedicated local kind cluster instead:

```bash
python tools/run_local_lab.py cleanup --delete-cluster --allow-local-lab
```

The second command deletes everything in the named local cluster. Do not reuse a cluster containing unrelated work. Output files under .local are retained. No Azure resources exist as a result of this script.

## Verification boundary

The Python contracts, metrics, collector behavior and ASGI response logic are tested offline. Docker, kind, kubectl and Go were unavailable in the preparation environment, so container builds, Go compilation and the complete live recording pipeline remain to be verified on the local machine. No recording or model result is pre-populated or claimed.
