"""Cross-platform local kind recorder. Never provisions Azure or targets an AKS context."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from readiness_agent.collector import collect
from readiness_agent.evaluation import evaluate
from readiness_agent.llm import ModelClient

NAMESPACE = "readiness-diag-lab"
OWNER = {"app.kubernetes.io/managed-by": "readiness-diagnostic-lab"}
SCENARIOS = ("healthy", "port", "path", "dependency", "timeout")
CAUSES = {"healthy": "healthy", "port": "probe_port_mismatch", "path": "probe_path_mismatch",
          "dependency": "dependency_unavailable", "timeout": "insufficient_evidence"}
FAULT_NEEDLES = {"port": "connection refused", "path": "statuscode: 404",
                 "dependency": "statuscode: 503", "timeout": "context deadline exceeded"}

# An application profile is one image plus the environment/arguments it runs with.
# "support" lists, per fault scenario, log substrings that independently support the
# injected cause. A profile without support for a scenario is recorded as an
# abstention control: the label follows the evidence, not the injection.
PROFILES = {
    "uvicorn": {"image": "uvicorn", "support": {
        "port": ("Uvicorn running on",), "path": ("Readiness route registered:",),
        "dependency": ("Readiness dependency inventory unavailable",)}},
    "go": {"image": "go", "support": {
        "port": ('msg="starting HTTP server"', "INFO starting HTTP server address="),
        "path": ("readiness_path=",),
        "dependency": ('msg="dependency check failed"', "ERROR dependency check failed dependency=")}},
    "go-json": {"image": "go", "env": {"LOG_FORMAT": "json"}, "support": {
        "port": ('"msg":"starting HTTP server"',), "path": ('"readiness_path":',),
        "dependency": ('"msg":"dependency check failed"',)}},
    "node": {"image": "node", "support": {
        "port": ("server listening on http://",), "path": ("routes mounted:",),
        "dependency": ("readiness check failed:",)}},
    "uvicorn-quiet": {"image": "uvicorn", "support": {
        "dependency": ("Readiness dependency inventory unavailable",)},
        "args": ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080",
                 "--no-use-colors", "--log-level", "warning"]},
}

# dev-v1 is the original eight-case recording. phase2 is the preregistered
# LLM-suitability matrix in docs/phase-2-protocol.md; keep the order stable.
MATRICES = {
    "dev-v1": [(f, s) for f in ("uvicorn", "go") for s in ("healthy", "port", "path", "dependency")],
    "phase2": [("go-json", s) for s in ("healthy", "port", "path", "dependency")]
              + [("node", s) for s in ("healthy", "port", "path", "dependency", "timeout")]
              + [("uvicorn-quiet", s) for s in ("port", "path", "dependency")]
              + [("go", "timeout")],
}

# Which evidence form the baseline rules were written for. The recorder stores this
# as label metadata so results can be split without re-deriving it after the fact.
COHORTS = {("uvicorn", "port"): "in-pattern", ("uvicorn", "path"): "in-pattern",
           ("uvicorn", "dependency"): "in-pattern", ("go", "port"): "in-pattern",
           ("go", "path"): "in-pattern", ("go", "dependency"): "in-pattern",
           ("uvicorn-quiet", "dependency"): "in-pattern"}


def cohort(profile, scenario):
    if scenario == "healthy":
        return "in-pattern"
    if scenario == "timeout" or scenario not in PROFILES[profile]["support"]:
        return "control"
    return COHORTS.get((profile, scenario), "out-of-pattern")


def execute(args, *, document=None, capture=True, timeout=180):
    result = subprocess.run(args, input=json.dumps(document) if document is not None else None,
                            capture_output=capture, text=True, timeout=timeout, cwd=ROOT)
    if result.returncode:
        raise ValueError(f"Command failed: {args[0]} {args[1]}; inspect the local tool/cluster")
    return result.stdout if capture else ""


def preflight():
    missing = [name for name in ("docker", "kind", "kubectl") if shutil.which(name) is None]
    if missing:
        raise ValueError("Missing tools: " + ", ".join(missing))
    execute(["docker", "info"], timeout=30)
    execute(["kind", "version"], timeout=15)
    execute(["kubectl", "version", "--client", "-o", "json"], timeout=15)


def kubectl(cluster, args, document=None):
    return execute(["kubectl", "--context", "kind-" + cluster, "--request-timeout=30s", *args], document=document)


def check_namespace(cluster):
    raw = kubectl(cluster, ["get", "namespace", NAMESPACE, "--ignore-not-found", "-o", "json"])
    if raw.strip():
        labels = json.loads(raw).get("metadata", {}).get("labels", {})
        if any(labels.get(k) != v for k, v in OWNER.items()):
            raise ValueError("Existing namespace is not owned by this lab")
    else:
        kubectl(cluster, ["create", "-f", "-"], {"apiVersion": "v1", "kind": "Namespace",
                "metadata": {"name": NAMESPACE, "labels": OWNER}})


def container(image, env=None, probe_port=8080, probe_path="/ready", args=None):
    item = {"name": "api", "image": image, "imagePullPolicy": "IfNotPresent",
            "env": [{"name": k, "value": v} for k, v in (env or {}).items()],
            "ports": [{"containerPort": 8080}],
            "startupProbe": {"httpGet": {"port": 8080, "path": "/live"},
                             "periodSeconds": 1, "timeoutSeconds": 3, "failureThreshold": 60},
            "readinessProbe": {"httpGet": {"port": probe_port, "path": probe_path},
                               "periodSeconds": 2, "timeoutSeconds": 3, "failureThreshold": 1},
            "resources": {"requests": {"cpu": "25m", "memory": "32Mi"},
                          "limits": {"cpu": "300m", "memory": "128Mi"}},
            "securityContext": {"allowPrivilegeEscalation": False, "readOnlyRootFilesystem": True,
                                "capabilities": {"drop": ["ALL"]}}}
    if args:
        item["args"] = list(args)
    return item


def pod_spec(item):
    return {"containers": [item], "automountServiceAccountToken": False,
            "securityContext": {"runAsNonRoot": True, "runAsUser": 10001,
                                "seccompProfile": {"type": "RuntimeDefault"}}}


def dependency_resources():
    item = container("readiness-diag-go:dev", {"ROLE": "dependency"}, probe_path="/health")
    return {"apiVersion": "v1", "kind": "List", "items": [
        {"apiVersion": "apps/v1", "kind": "Deployment",
         "metadata": {"name": "dependency", "namespace": NAMESPACE, "labels": OWNER},
         "spec": {"replicas": 1, "selector": {"matchLabels": {"app": "dependency"}},
                  "template": {"metadata": {"labels": {"app": "dependency"}}, "spec": pod_spec(item)}}},
        {"apiVersion": "v1", "kind": "Service",
         "metadata": {"name": "dependency", "namespace": NAMESPACE, "labels": OWNER},
         "spec": {"selector": {"app": "dependency"}, "ports": [{"port": 8080, "targetPort": 8080}]}}
    ]}


def case_document(profile, scenario):
    if profile not in PROFILES or scenario not in SCENARIOS:
        raise ValueError("Unsupported development scenario")
    spec = PROFILES[profile]
    env = {"READY_PATH": "/ready", "DEPENDENCY_URL": "http://dependency:8080/health", **spec.get("env", {})}
    if scenario == "timeout":
        # Longer than the probe's timeoutSeconds, shorter than the recording budget.
        env["READY_DELAY_SECONDS"] = "10"
    return {"apiVersion": "v1", "kind": "Pod",
            "metadata": {"name": f"{profile}-{scenario}", "namespace": NAMESPACE, "labels": OWNER},
            "spec": pod_spec(container(f"readiness-diag-{spec['image']}:dev", env,
                probe_port=9090 if scenario == "port" else 8080,
                probe_path="/wrong-readiness-path" if scenario == "path" else "/ready",
                args=spec.get("args")))}


def wait_for_fault(cluster, pod, scenario, seconds=90):
    needle = FAULT_NEEDLES[scenario]
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        snapshot = json.loads(kubectl(cluster, ["-n", NAMESPACE, "get", "pod", pod, "-o", "json"]))
        uid = snapshot["metadata"]["uid"]
        events = json.loads(kubectl(cluster, ["-n", NAMESPACE, "get", "events", "--field-selector",
                                            f"involvedObject.uid={uid}", "-o", "json"]))
        ready = any(c.get("type") == "Ready" and c.get("status") == "True"
                    for c in snapshot.get("status", {}).get("conditions", []))
        if not ready and any(needle in x.get("message", "").lower() for x in events.get("items", [])):
            return
        time.sleep(1)
    raise ValueError("Expected fault was not observed; no diagnostic label will be published")


def support_needles(scenario, profile=None):
    """Needles for one profile, or the union over all profiles when none is named."""
    profiles = [PROFILES[profile]] if profile else PROFILES.values()
    return tuple(n for spec in profiles for n in spec["support"].get(scenario, ()))


def supporting_log_options(bundle, scenario, profile=None):
    needles = support_needles(scenario, profile)
    return [[o.id] for o in bundle.observations if o.kind == "app_log"
            and any(needle in o.text for needle in needles)]


def required_evidence(profile, scenario):
    """Evidence IDs that must exist before a case is recorded at all."""
    if scenario == "healthy":
        return {"status"}
    if scenario == "dependency":
        return {"events", "logs"}
    if scenario == "timeout" or (profile and scenario not in PROFILES[profile]["support"]):
        return {"probe", "events"}
    return {"probe", "events", "startup"}


def collect_recording_evidence(cluster, pod, scenario, profile=None, seconds=30):
    """Wait for application evidence after a probe can fail before process startup."""
    required = required_evidence(profile, scenario)
    expects_support = bool(support_needles(scenario, profile))
    deadline = time.monotonic() + seconds
    while True:
        bundle = collect("kind-" + cluster, NAMESPACE, pod, "api")
        missing = required - {o.id for o in bundle.observations}
        supported = not expects_support or bool(supporting_log_options(bundle, scenario, profile))
        if not missing and supported:
            return bundle
        if time.monotonic() >= deadline:
            detail = ", ".join(sorted(missing)) or "cause-supporting application log"
            raise ValueError(f"Recording evidence timeout for {pod}: missing {detail}")
        time.sleep(1)


def label_for(bundle, profile, scenario):
    """Label what the recorded evidence supports; keep the injection as metadata.

    A fault whose supporting log never reached the bundle is labelled
    insufficient_evidence, per the held-out label policy in docs/evaluation.md.
    """
    label = {"cause": CAUSES[scenario], "required_evidence_ids": [], "split": "dev",
             "origin": "local-kind-recorded", "framework": profile, "scenario": scenario,
             "cohort": cohort(profile, scenario), "injected_fault": scenario}
    if scenario == "healthy":
        label["required_evidence_ids"] = ["status"]
    elif scenario != "timeout" and scenario in PROFILES[profile]["support"]:
        options = supporting_log_options(bundle, scenario, profile)
        if not options:
            raise ValueError("Cause-supporting application evidence is absent")
        label["required_evidence_ids"] = ["events"] if scenario == "dependency" else ["probe", "events"]
        label["evidence_options"] = options
    else:
        label["cause"] = "insufficient_evidence"
    return label


def record(cluster, output, create_cluster, matrix="dev-v1"):
    preflight()
    if matrix not in MATRICES:
        raise ValueError("Unknown recording matrix")
    plan = MATRICES[matrix]
    images_needed = sorted({PROFILES[profile]["image"] for profile, _ in plan} | {"go"})
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    status = {"status": "RECORDING", "origin": "local-kind", "started_utc": datetime.now(timezone.utc).isoformat(),
              "matrix": matrix, "frameworks": sorted({profile for profile, _ in plan}),
              "cases": [], "cluster_created": False}
    def save_status():
        (output / "recording.json").write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
    save_status()
    try:
        clusters = execute(["kind", "get", "clusters"]).splitlines()
        if cluster not in clusters:
            if not create_cluster:
                raise ValueError("Local kind cluster is missing; use --create-cluster")
            execute(["kind", "create", "cluster", "--name", cluster, "--wait", "120s"], capture=False, timeout=240)
            status["cluster_created"] = True
        check_namespace(cluster)
        images = {}
        for framework in images_needed:
            tag = f"readiness-diag-{framework}:dev"
            execute(["docker", "build", "-t", tag, str(ROOT / "lab" / framework)], capture=False, timeout=600)
            images[framework] = execute(["docker", "image", "inspect", tag, "--format", "{{.Id}}"]).strip()
            execute(["kind", "load", "docker-image", tag, "--name", cluster], capture=False, timeout=240)
        status["image_ids"] = images
        status["fixture_source_sha256"] = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                                           for p in sorted((ROOT / "lab").rglob("*"))
                                           if p.is_file() and "__pycache__" not in p.parts}
        kubectl(cluster, ["apply", "-f", "-"], dependency_resources())
        (output / "evidence").mkdir()
        (output / "labels").mkdir()
        for profile, scenario in plan:
            case_id = f"R{len(status['cases']) + 1:03d}"
            doc = case_document(profile, scenario)
            name = doc["metadata"]["name"]
            kubectl(cluster, ["-n", NAMESPACE, "scale", "deployment", "dependency", "--replicas=1"])
            kubectl(cluster, ["-n", NAMESPACE, "rollout", "status", "deployment/dependency", "--timeout=90s"])
            if scenario == "dependency":
                kubectl(cluster, ["-n", NAMESPACE, "scale", "deployment", "dependency", "--replicas=0"])
                # The subsequent 503 observation confirms the dependency fault;
                # do not use 'wait --for=delete', which fails if no Pods already remain.
            kubectl(cluster, ["-n", NAMESPACE, "delete", "pod", name, "--ignore-not-found", "--wait=true"])
            kubectl(cluster, ["create", "-f", "-"], doc)
            kubectl(cluster, ["-n", NAMESPACE, "wait", "--for=jsonpath={.status.phase}=Running", "pod/" + name, "--timeout=90s"])
            if scenario == "healthy":
                kubectl(cluster, ["-n", NAMESPACE, "wait", "--for=condition=Ready", "pod/" + name, "--timeout=90s"])
            else:
                wait_for_fault(cluster, name, scenario)
            bundle = collect_recording_evidence(cluster, name, scenario, profile)
            if not required_evidence(profile, scenario) <= {o.id for o in bundle.observations}:
                raise ValueError("Required recording evidence is missing; inspect collector limitations")
            label = label_for(bundle, profile, scenario)
            (output / "evidence" / f"{case_id}.json").write_text(json.dumps(bundle.to_dict(), indent=2) + "\n", encoding="utf-8")
            (output / "labels" / f"{case_id}.json").write_text(json.dumps(label, indent=2) + "\n", encoding="utf-8")
            status["cases"].append({"id": case_id, "framework": profile, "scenario": scenario,
                                     "cohort": label["cohort"], "labelled_cause": label["cause"],
                                     "recorded_utc": datetime.now(timezone.utc).isoformat()})
            save_status()
            kubectl(cluster, ["-n", NAMESPACE, "delete", "pod", name, "--wait=true"])
        kubectl(cluster, ["-n", NAMESPACE, "scale", "deployment", "dependency", "--replicas=0"])
        status["status"] = "RECORDED"
    except Exception:
        status["status"] = "SETUP_OR_RECORDING_ERROR"
        raise
    finally:
        save_status()
    print(f"Recorded {len(status['cases'])} development cases in {output}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check")
    rec = sub.add_parser("record")
    rec.add_argument("--output", required=True)
    rec.add_argument("--create-cluster", action="store_true")
    rec.add_argument("--matrix", choices=sorted(MATRICES), default="dev-v1")
    clean = sub.add_parser("cleanup")
    clean.add_argument("--delete-cluster", action="store_true")
    for command in (rec, clean):
        command.add_argument("--cluster", default="readiness-diag")
        command.add_argument("--allow-local-lab", action="store_true")
    pilot = sub.add_parser("pilot")
    pilot.add_argument("--cases", required=True)
    pilot.add_argument("--output", required=True)
    pilot.add_argument("--repetitions", type=int, default=3)
    pilot.add_argument("--variants", default="A1")
    pilot.add_argument("--allow-model-calls", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "check":
            preflight()
            print("Docker, kind and kubectl are available. No resources created.")
        elif args.command == "pilot":
            variants = args.variants.split(",")
            if set(variants) - {"A1"} and not args.allow_model_calls:
                raise ValueError("Use --allow-model-calls for chargeable requests")
            client = ModelClient.from_env() if set(variants) - {"A1"} else None
            result = evaluate(args.cases, args.output, variants, client=client, repetitions=args.repetitions)
            print(json.dumps(result, indent=2))
            return 1 if any(v["errors"] for v in result["variants"].values()) else 0
        else:
            if not args.allow_local_lab or not re.fullmatch(r"[a-z][a-z0-9-]{0,39}", args.cluster):
                raise ValueError("Use a valid local cluster name and --allow-local-lab")
            if args.command == "record":
                record(args.cluster, args.output, args.create_cluster, args.matrix)
            else:
                preflight()
                if args.cluster not in execute(["kind", "get", "clusters"]).splitlines():
                    raise ValueError("Named local kind cluster not found")
                check_namespace(args.cluster)
                if args.delete_cluster:
                    execute(["kind", "delete", "cluster", "--name", args.cluster], capture=False)
                else:
                    kubectl(args.cluster, ["delete", "namespace", NAMESPACE])
        return 0
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print(f"Local lab stopped: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
