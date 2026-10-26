"""A deliberately explicit baseline; no commands or recommendations are executed."""
import json
import re

from .models import Diagnosis


def diagnose(bundle):
    configs = []
    failures = [o for o in bundle.observations if o.kind == "probe_result"]
    logs = [o for o in bundle.observations if o.kind == "app_log"]
    for o in bundle.observations:
        if o.kind == "probe_config":
            try:
                value = json.loads(o.text)
                if (type(value.get("port")) is int and isinstance(value.get("path"), str)
                        and value.get("scheme", "HTTP") == "HTTP"):
                    configs.append((o, value))
            except (ValueError, AttributeError):
                pass
    candidates = []
    for config, value in configs:
        for failure in failures:
            for log in logs:
                listeners = re.findall(r"Listening on 0\.0\.0\.0:(\d+)\b", log.text)
                listeners += re.findall(r"Uvicorn running on http://(?:0\.0\.0\.0|127\.0\.0\.1):(\d+)\b", log.text)
                listeners += re.findall(r'msg="starting HTTP server" address=:(\d+)\b', log.text)
                routes = re.findall(r"Readiness endpoint: (/[^\s]+)", log.text)
                routes += re.findall(r"Readiness route registered: GET (/[^\s]+)", log.text)
                routes += re.findall(r'readiness_path=(/[^\s"]+)', log.text)
                if (listeners and "connection refused" in failure.text.lower()
                        and all(int(p) != value["port"] for p in listeners)):
                    candidates.append(("probe_port_mismatch", [config.id, failure.id, log.id],
                                       "Probe port differs from the logged listener.",
                                       "Verify the listener and configure the readiness probe port accordingly."))
                if (len(set(routes)) == 1 and "statuscode: 404" in failure.text.lower()
                        and routes[0] != value["path"]):
                    candidates.append(("probe_path_mismatch", [config.id, failure.id, log.id],
                                       "Probe path differs from the logged readiness endpoint.",
                                       "Verify the readiness route and configure the probe path accordingly."))
    for failure in failures:
        if "statuscode: 503" in failure.text.lower():
            for log in logs:
                match = re.search(r'Dependency check failed: ([a-zA-Z0-9_-]+)\b|Readiness dependency ([a-zA-Z0-9_-]+) unavailable|msg="dependency check failed" dependency=([a-zA-Z0-9_-]+)', log.text)
                if match:
                    candidates.append(("dependency_unavailable", [failure.id, log.id],
                                       "Application readiness reports a failed dependency check.",
                                       "Inspect the reported dependency; do not assume a network or credential cause."))
    healthy = [o for o in bundle.observations if o.kind == "pod_status" and o.text == "Ready=True"]
    unready = [o for o in bundle.observations if o.kind == "pod_status" and o.text == "Ready=False"]
    causes = {c[0] for c in candidates}
    if len(causes) == 1 and not healthy and not any(o.id == "container-scope" for o in bundle.observations):
        cause, ids, summary, advice = candidates[0]
        return Diagnosis(cause, summary, tuple(ids), advice,
                         "Snapshot-level inference; logs may be stale or misleading. Verify before changing configuration.")
    if healthy and not unready and not failures and not candidates:
        return Diagnosis("healthy", "The recorded Pod readiness condition is true.",
                         (healthy[0].id,), "No corrective action from this snapshot.",
                         "Readiness is not proof of business correctness or future availability.")
    return Diagnosis("insufficient_evidence", "The explicit rules cannot establish one supported cause.",
                     tuple(o.id for o in bundle.observations if o.kind in ("probe_result", "limitation")),
                     "Collect a current probe result, effective configuration and application readiness logs.",
                     "Evidence may be missing, contradictory or outside the supported fault classes.")
