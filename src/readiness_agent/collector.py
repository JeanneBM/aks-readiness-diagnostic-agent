"""Bounded kubectl reads: current status, sorted Events, recent logs and startup prefix."""
from datetime import datetime
import json
import re
import subprocess
import threading

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


def read_prefix(command, limit=16000, timeout=20):
    """Read the beginning of the available log stream, not the last --limit-bytes."""
    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    except OSError:
        return None, False
    data = []
    def reader():
        try:
            data.append(process.stdout.read(limit + 1))
        except OSError:
            pass
    thread = threading.Thread(target=reader, daemon=True)
    thread.start()
    thread.join(timeout)
    timed_out = thread.is_alive()
    truncated = bool(data and len(data[0]) > limit)
    if timed_out or truncated:
        process.kill()
    try:
        code = process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
        code = -1
    thread.join(2)
    process.stdout.close()
    if timed_out or not data or (code != 0 and not truncated):
        return None, False
    return data[0][:limit].decode("utf-8", errors="replace"), truncated


def event_time(item):
    value = (item.get("series", {}).get("lastObservedTime") or item.get("lastTimestamp")
             or item.get("eventTime") or item.get("metadata", {}).get("creationTimestamp"))
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except (AttributeError, TypeError, ValueError):
        return float("-inf")


def collect(context, namespace, pod, container, run=None, prefix_reader=None):
    for value in (namespace, pod, container):
        if not NAME.fullmatch(value) or len(value) > 253:
            raise ValueError("Invalid Kubernetes target name")
    if not context or context.startswith("-") or len(context) > 300:
        raise ValueError("An explicit kubeconfig context is required")
    prefix = ["kubectl", "--context", context, "--namespace", namespace, "--request-timeout=15s"]
    run = run or subprocess.run
    prefix_reader = prefix_reader or read_prefix

    def read(args, *, optional=False):
        try:
            result = run([*prefix, *args], capture_output=True, text=True, timeout=20, check=False)
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
    containers = snapshot.get("spec", {}).get("containers", [])
    selected = next((x for x in containers if x.get("name") == container), None)
    if selected is None:
        raise ValueError("Container is absent from the named Pod")
    conditions = snapshot.get("status", {}).get("conditions", [])
    ready = next((x.get("status") for x in conditions if x.get("type") == "Ready"), "Unknown")
    obs = [{"id": "status", "kind": "pod_status", "source": "pod/status", "text": f"Ready={ready}"}]
    def limitation(id, text):
        obs.append({"id": id, "kind": "limitation", "source": "collector", "text": text})
    if len(containers) != 1:
        limitation("container-scope", "Pod-level readiness Events cannot be reliably attributed to the selected container.")
    http = selected.get("readinessProbe", {}).get("httpGet")
    if http:
        port = http.get("port")
        if isinstance(port, str):
            port = next((p.get("containerPort") for p in selected.get("ports", []) if p.get("name") == port), port)
        obs.append({"id": "probe", "kind": "probe_config", "source": "pod/spec/readinessProbe",
                    "text": json.dumps({"path": http.get("path", "/"), "port": port,
                                        "scheme": http.get("scheme", "HTTP")})})
    else:
        limitation("probe-limit", "No supported HTTP readiness probe; exec, TCP and gRPC probes are outside this version.")
    uid = snapshot.get("metadata", {}).get("uid")
    events = read(["get", "events", "--field-selector", f"involvedObject.uid={uid}", "-o", "json"], optional=True) if uid else None
    if events is not None:
        items = sorted(json.loads(events).get("items", []), key=event_time)
        messages = [x.get("message", "") for x in items
                    if "readiness probe failed" in x.get("message", "").lower()]
        if messages:
            obs.append({"id": "events", "kind": "probe_result", "source": "pod/events/time-ordered",
                        "text": redact("\n".join(messages[-10:]))[:16000]})
        else:
            limitation("events-empty", "No readiness failure Events were available; absence is not proof of health.")
    else:
        limitation("events-limit", "Pod Events were unavailable.")
    logs = read(["logs", pod, "--container", container, "--tail=100", "--limit-bytes=16000",
                 "--since=10m", "--timestamps=true"], optional=True)
    if logs and logs.strip():
        obs.append({"id": "logs", "kind": "app_log", "source": "container/logs/recent-10m",
                    "text": redact(logs)[:16000]})
    else:
        limitation("logs-limit", "Recent logs unavailable." if logs is None else "No log lines in the recent ten-minute window.")
    startup, truncated = prefix_reader([*prefix, "logs", pod, "--container", container,
                                        "--tail=-1", "--timestamps=true"])
    if startup and startup.strip():
        obs.append({"id": "startup", "kind": "app_log", "source": "container/logs/available-prefix",
                    "text": redact(startup)[:16000]})
        if truncated:
            limitation("startup-truncated", "Startup log prefix was truncated at 16000 bytes.")
    else:
        limitation("startup-limit", "Startup log prefix unavailable." if startup is None else "No startup log lines were available.")
    limitation("snapshot-limit", "Sequential reads are not atomic. Logs may be stale or rotated; the prefix is the beginning of available current-container logs, not guaranteed original startup.")
    return Bundle.parse({"schema": 1, "target": "selected-pod/selected-container", "observations": obs})
