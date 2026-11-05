# Security controls and verification

## Collector identity

`k8s/collector-readonly.json` is an opt-in example for the existing `readiness-diag-lab` namespace: one ServiceAccount, Role and RoleBinding. It grants only core `pods get`, `pods/log get`, and `events list`. There are no mutation, Secret, exec, role-management or cluster-wide grants. No token Secret is created and automatic Pod token mounting is disabled.

An administrator can apply it to the intended lab context:

```bash
kubectl --context YOUR_LAB_CONTEXT apply -f k8s/collector-readonly.json
```

The collector still uses the credentials in its explicitly selected kubeconfig context; applying this file does not change the operator identity. Supply a dedicated kubeconfig with short-lived credentials for this ServiceAccount, or equivalent restricted Entra credentials, before collection. Do not commit kubeconfigs or tokens. If running in a Pod, explicitly project a short-lived token; automount is disabled by default. Kubernetes permissions are additive: extra bindings to the same identity or groups can broaden access. The namespace-wide example can read logs from any Pod in that namespace; it is not limited to one Pod name. Use a dedicated namespace without unrelated workloads.

## Security workflow

`.github/workflows/security.yml` runs on main pushes, pull requests and manual dispatch. It has no Azure or model credentials and makes no model requests.

- CodeQL security-extended queries analyze Python and Go and publish findings in GitHub Code scanning. A successful analysis job alone does not mean zero findings or enforce a merge block on findings.
- Trivy filesystem scanning fails on HIGH/CRITICAL dependency vulnerabilities, including unfixed ones. A separate current-tree secret scan fails on all detected secret severities. No blanket source/test exclusions or vulnerability suppression are configured. Findings require review; a passing scan is not proof that secrets or vulnerabilities are absent.
- Static contracts prevent broadening the example RBAC and check that direct workflow action references use full commit SHAs.
- A disposable kind cluster verifies allowed reads and denied mutations, Secret reads and cross-namespace access using impersonated authorization checks. It does not validate Entra authentication or a deployed AKS identity.

CodeQL alone receives `security-events: write` for result upload. Other jobs have `contents: read`; checkout does not persist Git credentials. Direct Action references are pinned; Dependabot proposes Action and Uvicorn dependency updates. Scanner binaries/databases and transitive action dependencies remain external supply-chain inputs. Trivy version is fixed explicitly and must be reviewed for updates.

The filesystem scan checks supported dependency manifests, not built container OS packages or complete Git history. Container image scanning, history-wide secret scanning and branch rules are outside this workflow. Configure branch protection/rulesets separately if these jobs must be required before merge; workflow creation does not enable that policy.

## Data boundaries

Recommendations are text, never executed by an LLM tool. Collected logs are bounded and common secret patterns are redacted, but regex redaction and prompt instructions are not confidentiality or prompt-injection guarantees. Review evidence before provider submission. Azure API keys stay in local environment variables; Entra model authentication is not implemented. Provider diagnostics retain allowlisted metadata only. Do not publish raw logs or provider bodies.
