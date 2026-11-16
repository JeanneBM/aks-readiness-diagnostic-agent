"""Generate the 13-case phase-2 matrix as offline fixtures, never as a reported result.

Application log text comes from the committed native captures under tests/golden
(real Go and Node stdout). Pod status, probe configuration and kubelet Event text are
assembled here. The fixtures let A1 and the H fallback be exercised without a cluster
or a model; the reported phase-2 result must come from a kind recording.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from run_local_lab import CAUSES, MATRICES, PROFILES, cohort, supporting_log_options  # noqa: E402
sys.path.insert(0, str(ROOT / "src"))
from readiness_agent.models import Bundle  # noqa: E402

GOLDEN = ROOT / "tests/golden"
EVENTS = {
    "port": 'Readiness probe failed: Get "http://192.0.2.7:9090/ready": dial tcp 192.0.2.7:9090: connect: connection refused',
    "path": "Readiness probe failed: HTTP probe failed with statuscode: 404",
    "dependency": "Readiness probe failed: HTTP probe failed with statuscode: 503",
    "timeout": 'Readiness probe failed: Get "http://192.0.2.7:8080/ready": context deadline exceeded (Client.Timeout exceeded while awaiting headers)',
}
SNAPSHOT_LIMIT = ("Sequential reads are not atomic. Logs may be stale or rotated; the prefix is the beginning "
                  "of available current-container logs, not guaranteed original startup.")


def golden(name):
    return (GOLDEN / name).read_text(encoding="utf-8")


def application_log(profile, scenario):
    """Real captured stdout for the closest native run; None when the app logged nothing."""
    if profile == "go-json":
        lines = golden("go-json-handler.log").splitlines()
        return "\n".join(lines if scenario == "dependency" else lines[:1]) + "\n"
    if profile == "go":
        return golden("go-text-handler.log").splitlines()[0] + "\n"
    if profile == "node":
        name = {"dependency": "node-dependency-down.log", "timeout": "node-ready-delay.log"}.get(scenario, "node-dependency-up.log")
        lines = golden(name).splitlines()
        if scenario in ("port", "path"):
            # The probe never reaches /ready in these injections, so no such request is logged.
            lines = [x for x in lines if "GET /ready ->" not in x]
        if scenario == "path":
            lines.append(lines[-1].replace("GET /live -> 200", "GET /wrong-readiness-path -> 404"))
        return "\n".join(lines) + "\n"
    if profile == "uvicorn-quiet":
        return "ERROR:    Readiness dependency inventory unavailable: <urlopen error [Errno 111] Connection refused>\n" \
            if scenario == "dependency" else None
    raise ValueError(profile)


def observations(profile, scenario):
    obs = [{"id": "status", "kind": "pod_status", "source": "synthetic/pod/status",
            "text": "Ready=True" if scenario == "healthy" else "Ready=False"},
           {"id": "probe", "kind": "probe_config", "source": "synthetic/pod/spec/readinessProbe",
            "text": json.dumps({"path": "/wrong-readiness-path" if scenario == "path" else "/ready",
                                "port": 9090 if scenario == "port" else 8080, "scheme": "HTTP"})}]
    if scenario == "healthy":
        obs.append({"id": "events-empty", "kind": "limitation", "source": "collector",
                    "text": "No readiness failure Events were available; absence is not proof of health."})
    else:
        obs.append({"id": "events", "kind": "probe_result", "source": "synthetic/pod/events/time-ordered",
                    "text": EVENTS[scenario]})
    log = application_log(profile, scenario)
    if log:
        obs.append({"id": "logs", "kind": "app_log", "source": "synthetic/container/logs/recent-10m", "text": log})
        obs.append({"id": "startup", "kind": "app_log", "source": "synthetic/container/logs/available-prefix", "text": log})
    else:
        obs.append({"id": "logs-limit", "kind": "limitation", "source": "collector",
                    "text": "No log lines in the recent ten-minute window."})
        obs.append({"id": "startup-limit", "kind": "limitation", "source": "collector",
                    "text": "No startup log lines were available."})
    obs.append({"id": "snapshot-limit", "kind": "limitation", "source": "collector", "text": SNAPSHOT_LIMIT})
    return obs


def generate(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    (output / "evidence").mkdir()
    (output / "labels").mkdir()
    for index, (profile, scenario) in enumerate(MATRICES["phase2"], 1):
        bundle = Bundle.parse({"schema": 1, "target": "selected-pod/selected-container",
                               "observations": observations(profile, scenario)})
        label = {"cause": CAUSES[scenario], "required_evidence_ids": [], "split": "dev",
                 "origin": "synthetic-development", "framework": profile, "scenario": scenario,
                 "cohort": cohort(profile, scenario), "injected_fault": scenario}
        if scenario == "healthy":
            label["required_evidence_ids"] = ["status"]
        elif scenario != "timeout" and scenario in PROFILES[profile]["support"]:
            options = supporting_log_options(bundle, scenario, profile)
            if not options:
                raise ValueError(f"Captured log does not support {profile}/{scenario}")
            label["required_evidence_ids"] = ["events"] if scenario == "dependency" else ["probe", "events"]
            label["evidence_options"] = options
        else:
            label["cause"] = "insufficient_evidence"
        name = f"S{index:03d}.json"
        (output / "evidence" / name).write_text(json.dumps(bundle.to_dict(), indent=2) + "\n", encoding="utf-8")
        (output / "labels" / name).write_text(json.dumps(label, indent=2) + "\n", encoding="utf-8")
    print(f"Generated {len(MATRICES['phase2'])} synthetic phase-2 cases in {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, help="New directory; existing directories are refused")
    generate(parser.parse_args().output)
