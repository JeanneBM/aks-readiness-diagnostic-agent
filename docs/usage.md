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

Use a model supporting Chat Completions, strict JSON schema output, temperature and max_tokens. Not all provider models or Azure regions are supported. This version uses API keys; managed identity is not implemented.

```bash
python -m readiness_agent.cli diagnose data/dev/evidence/D001.json --variant C1 --allow-model-calls
python -m readiness_agent.cli evaluate --cases data/dev --variants A1,C1,H --allow-model-calls --output .local/runs/paired-dev-001
```

C1 and H are independent runs; H can make an additional request on cases where A1 abstains. Temperature zero does not guarantee deterministic output. There are no warm-up requests or retries. HTTP errors, timeouts, refusals and malformed outputs remain errors. The request timeout is 45 seconds; full runs can take much longer.

The manifest stores provider, model/deployment, API version and an endpoint hash, never the key. It does not pin the provider's immutable model version. Preserve deployment metadata separately for reproducibility.

## Freeze

```bash
python -m readiness_agent.cli freeze --cases data/dev --output .local/frozen-dev.json
python -m readiness_agent.cli evaluate --cases data/dev --variants A1 --manifest .local/frozen-dev.json --output .local/runs/frozen-dev-001
```

For model runs, freeze with --include-model-config and use the same provider configuration during replay. Hashes cover package source, JSON cases, prompt and output schema. The manifest also records Python version and model configuration. This detects drift; it does not certify independent held-out preparation.

## Optional cluster collection

Install kubectl and use a disposable cluster you are authorized to inspect. The context is explicit and the tool never switches your current context.

```bash
python -m readiness_agent.cli collect --context YOUR_CONTEXT --namespace readiness-lab --pod readiness-demo --container api --output .local/bundles/demo-001.json --allow-cluster-read
python -m readiness_agent.cli diagnose .local/bundles/demo-001.json
```

Reads: named Pod, namespace Events filtered by Pod UID, and named-container logs. Required permissions are supplied externally: pods get, events list, pods/log get. No RBAC is granted by the repository.

Only selected HTTP probe configuration and Pod status are retained. Environment values, annotations, Secret objects, raw Pod objects and node addresses are excluded. Logs are bounded to 100 lines, 16 KB and ten minutes. Event text is bounded but may contain older failures. Collection is sequential, not atomic. Previous-container logs, rollout history, metrics and dependency probes are not yet collected.

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
