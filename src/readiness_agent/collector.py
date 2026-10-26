"""Explicit, bounded kubectl reads of one named Pod and one named container."""
import json
import re
import subprocess

from .models import Bundle

NAME = re.compile(r"[a-z0-9](?:[-a-z0-9.]*[a-z0-9])?\Z")


def redact(text):
    text = re.sub(r"-----BEGIN [^-]*PRIVATE KEY-----.*?-----END [^-]*PRIVATE KEY-----",
                  "REDACTED_PRIVATE_KEY", text, flags=re.S)
    text = re.sub(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]+",
                  "REDACTED_TOKEN", text)
    text = re.sub(r"(?i)(Bearer\s+)\S+", r"\1REDACTED", text)
    text = re.sub(r"(?i)((?:password|api[_-]?key|token|client[_-]?secret|authorization)"
                  r"[\"']?\s*[:=]\s*)[^\s,;]+", r"\1REDACTED", text)
    text = re.sub(r"(?i)([?&](?:sig|token|key|code)=)[^&\s]+", r"\1REDACTED", text)
    text = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "REDACTED_EMAIL", text)
    text = re.sub(r"(?i)\b[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}\b", "REDACTED_UUID", text)
    return text


def collect(context, namespace, pod, container, run=None):
    for value in (namespace, pod, container):
        if not NAME.fullmatch(value) or len(value) > 253:
            raise ValueError("Invalid Kubernetes target name")
    if not context or context.startswith("-") or len(context) > 300:
        raise ValueError("An explicit kubeconfig context is required")
    run = run or subprocess.run

    def read(args, *, optional=False):
        try:
            result = run(["kubectl", "--context", context, "--namespace", namespace,
                          "--request-timeout=15s", *args],
                         capture_output=True, text=True, timeout=20, check=False)
        except (subprocess.TimeoutExpired, OSError):
            if optional:
                return None
            raise ValueError("kubectl read failed; verify context and read permissions") from None
        if result.returncode or len(result.stdout.encode()) > 2_000_000:
            if optional:
                return None
            raise ValueError("kubectl read failed or exceeded the response budget")
        return result.stdout

    snapshot = json.loads(read(["get", "pod", pod, "-o", "json"]))
    selected = next((x for x in snapshot.get("spec", {}).get("containers", [])
                     if x.get("name") == container), None)
    if selected is None:
        raise ValueError("Container is absent from the named Pod")
    conditions = snapshot.get("status", {}).get("conditions", [])
    ready = next((x.get("status") for x in conditions if x.get("type") == "Ready"), "Unknown")
    obs = [{"id": "status", "kind": "pod_status", "source": "pod/status", "text": f"Ready={ready}"}]
    http = selected.get("readinessProbe", {}).get("httpGet")
    if http:
        port = http.get("port")
        if isinstance(port, str):
            port = next((p.get("containerPort") for p in selected.get("ports", [])
                         if p.get("name") == port), port)
        obs.append({"id": "probe", "kind": "probe_config", "source": "pod/spec/readinessProbe",
                    "text": json.dumps({"path": http.get("path", "/"), "port": port,
                                        "scheme": http.get("scheme", "HTTP")})})
    else:
        obs.append({"id": "probe-limit", "kind": "limitation", "source": "collector",
                    "text": "No supported HTTP readiness probe; exec, TCP and gRPC probes are outside this version."})
    uid = snapshot.get("metadata", {}).get("uid")
    events = read(["get", "events", "--field-selector", f"involvedObject.uid={uid}", "-o", "json"], optional=True) if uid else None
    if events is not None:
        items = json.loads(events).get("items", [])
        # Only readiness failures are relevant; liveness failures must not masquerade as readiness.
        messages = [x.get("message", "") for x in items
                    if "readiness probe failed" in x.get("message", "").lower()]
        if messages:
            obs.append({"id": "events", "kind": "probe_result", "source": "pod/events",
                        "text": redact("\n".join(messages[-10:]))[:16000]})
    else:
        obs.append({"id": "events-limit", "kind": "limitation", "source": "collector",
                    "text": "Pod Events were unavailable; no failure cause can be inferred from absence."})
    logs = read(["logs", pod, "--container", container, "--tail=100", "--limit-bytes=16000",
                 "--since=10m"], optional=True)
    if logs and logs.strip():
        obs.append({"id": "logs", "kind": "app_log", "source": "container/logs",
                    "text": redact(logs)[:16000]})
    elif logs is None:
        obs.append({"id": "logs-limit", "kind": "limitation", "source": "collector",
                    "text": "Application logs were unavailable."})
    # Exclude environment values, annotations, Secret contents, UID, node and host addresses.
    return Bundle.parse({"schema": 1, "target": "selected-pod/selected-container", "observations": obs})
