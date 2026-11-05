# Usage

Install from the repository root with Python 3.11 or newer: `python -m pip install -e .`.

## Offline replay

```bash
python -m readiness_agent.cli diagnose data/dev/evidence/D001.json
python -m readiness_agent.cli evaluate --cases data/dev --variants A1 --output .local/runs/a1-dev-001
```

Each run writes a manifest, one result per case/variant, summary.json and summary.md. Use a new output directory. Exit codes: 0 for completed execution, 1 if any diagnosis has ERROR, 2 for setup/argument failure. A wrong but well-formed diagnosis affects scores; exit 0 does not mean all causes were correct.

## Optional model calls

Set these environment variables locally. Never commit credentials.

| Variable | Meaning |
| --- | --- |
| READINESS_PROVIDER | azure (default) or openai |
| READINESS_ENDPOINT | HTTPS Azure OpenAI resource root or HTTPS OpenAI API root; no path/query |
| READINESS_API_KEY | Provider credential |
| READINESS_MODEL | Azure deployment name or OpenAI model identifier |
| READINESS_API_VERSION | Azure API version; default 2024-10-21 |

Use a model supporting Chat Completions and strict JSON schema output. For deployments requiring newer request parameters, set READINESS_TOKEN_PARAMETER=max_completion_tokens and READINESS_TEMPERATURE=omit. Defaults remain max_tokens and temperature zero. No automatic parameter fallback or retry is performed. This version uses API keys; Entra/managed identity remains unimplemented.

```bash
python -m readiness_agent.cli diagnose data/dev/evidence/D001.json --variant C1 --allow-model-calls
python -m readiness_agent.cli evaluate --cases data/dev --variants A1,C1,H --repetitions 3 --allow-model-calls --output .local/runs/paired-dev-001
```

C1 and H are independent runs; H can make an additional request on cases where A1 abstains. Temperature zero does not guarantee deterministic output. There are no warm-up requests or retries. HTTP errors, timeouts, refusals and malformed outputs remain errors. The request timeout is 45 seconds; full runs can take much longer.

Optional pacing: set `READINESS_MIN_REQUEST_INTERVAL_SECONDS` to a number from 0 to 60 (default 0). This enforces a minimum interval between request starts within one sequential client, including failed calls; it does not retry requests or guarantee quota compliance. The setting is recorded in new manifests. Old freezes must be regenerated after this implementation change.

Provider errors now preserve allowlisted `provider_error` metadata: HTTP status, integer Retry-After from 0 to 3600 seconds, or a transport category (`timeout` / `connection`). HTTP-date Retry-After values, raw bodies, exception text, URLs and credentials are not stored. A missing field means unavailable information, not zero wait. Historical pilot errors cannot be reconstructed.

Per-attempt scores expose `cause_mismatch` and `citation_coverage_gap` separately. Existing `unsupported_conclusion` and `diagnostic_risk` retain their conservative scoring meaning; they are not human semantic judgments. Original pilot files remain unchanged.

The manifest stores provider, model/deployment, API version and an endpoint hash, never the key. It does not pin the provider's immutable model version. Preserve deployment metadata separately for reproducibility.

## Freeze

```bash
python -m readiness_agent.cli freeze --cases data/dev --output .local/frozen-dev.json
python -m readiness_agent.cli evaluate --cases data/dev --variants A1 --manifest .local/frozen-dev.json --output .local/runs/frozen-dev-001
```

For model runs, freeze with --include-model-config. Schema-2 manifests separate dataset identity from the frozen implementation. Held-out replay uses the earlier development manifest: code, prompt, runtime and model settings must match, while new dataset hashes are recorded separately. Development replay still requires full equality. Old schema-1 manifests must be regenerated. This detects drift, not independent authorship or chronology.

## Optional cluster collection

Install kubectl and use a disposable cluster you are authorized to inspect. The context is explicit and the tool never switches your current context.

```bash
python -m readiness_agent.cli collect --context YOUR_CONTEXT --namespace readiness-lab --pod readiness-demo --container api --output .local/bundles/demo-001.json --allow-cluster-read
python -m readiness_agent.cli diagnose .local/bundles/demo-001.json
```

Reads: named Pod, namespace Events filtered by Pod UID, and named-container logs. Required permissions are supplied externally: pods get, events list, pods/log get. No RBAC is granted by the repository.

Only selected HTTP probe configuration and Pod status are retained. Environment values, annotations, Secret objects, raw Pod objects and node addresses are excluded. Recent logs are bounded to 100 lines, 16 KB and ten minutes. A separate streaming read retains the first 16 KB of available current-container logs without a recent-window filter; it has a parent timeout and stops reading at the budget. Empty, unavailable and truncated windows are explicit limitations. Original startup can still be lost to log rotation. Events are sorted by their latest observation timestamp before selecting ten messages. Collection is sequential, not atomic. Previous-container logs, rollout history and metrics are not yet collected.

Inspect bundles before sending them to a provider. Redaction handles common credential patterns but cannot recognize every secret, hostname or personal detail. All evidence text is treated as untrusted. There is no execution path for recommendations.

## Disposable demo

The application simulates dependency failure; it does not test a real database integration.

```bash
docker build -t readiness-demo:local demo
docker run --rm -p 8080:8080 readiness-demo:local
```

For a local kind cluster, load the image and apply the manifest:

```bash
kind load docker-image readiness-demo:local --name YOUR_KIND_CLUSTER
kubectl --context YOUR_CONTEXT create namespace readiness-lab
kubectl --context YOUR_CONTEXT apply -f demo/pod.yaml
```

For AKS, build/push to your own registry and replace the local image reference. No registry or pull credentials are provisioned.

To create a fault, edit demo/pod.yaml: change the probe port, change the probe path, or set SIMULATE_DEPENDENCY_FAILURE to true. Leave the application's own port/path unchanged for mismatch cases. Recreate the standalone Pod when changing immutable fields. Use only the disposable lab.

```bash
kubectl --context YOUR_CONTEXT delete namespace readiness-lab
```

This deletes the disposable namespace, not billable Azure resources such as AKS or ACR.

## Safe output and portable code fingerprints

New provider requests restrict evidence IDs to the current bundle and recommendations to fixed templates. The adapter replaces the returned recommendation with the template for the parsed cause even if a provider ignores the strict schema. Model summaries and uncertainty remain untrusted text; do not copy commands from them. ID validity is not semantic evidence support.

Python source hashes use UTF-8 with normalized LF newlines (`code_hash_format: utf8-lf-v1`). `.gitattributes` also requests LF for Python checkouts. Dataset hashes still use original bytes. Python patch versions intentionally remain strict for freeze checks; recreate a development freeze after a runtime or implementation change. Historical manifests remain historical and are not rewritten.
