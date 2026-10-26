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
SCENARIOS = ("healthy", "port", "path", "dependency")


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


def container(image, env=None, probe_port=8080, probe_path="/ready"):
    return {"name": "api", "image": image, "imagePullPolicy": "IfNotPresent",
            "env": [{"name": k, "value": v} for k, v in (env or {}).items()],
            "ports": [{"containerPort": 8080}],
            "readinessProbe": {"httpGet": {"port": probe_port, "path": probe_path},
                               "periodSeconds": 2, "timeoutSeconds": 3, "failureThreshold": 1},
            "resources": {"requests": {"cpu": "25m", "memory": "32Mi"},
                          "limits": {"cpu": "300m", "memory": "128Mi"}},
            "securityContext": {"allowPrivilegeEscalation": False, "readOnlyRootFilesystem": True,
                                "capabilities": {"drop": ["ALL"]}}}


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


def case_document(framework, scenario):
    if framework not in ("uvicorn", "go") or scenario not in SCENARIOS:
        raise ValueError("Unsupported development scenario")
    return {"apiVersion": "v1", "kind": "Pod",
            "metadata": {"name": f"{framework}-{scenario}", "namespace": NAMESPACE, "labels": OWNER},
            "spec": pod_spec(container(f"readiness-diag-{framework}:dev",
                {"READY_PATH": "/ready", "DEPENDENCY_URL": "http://dependency:8080/health"},
                probe_port=9090 if scenario == "port" else 8080,
                probe_path="/wrong-readiness-path" if scenario == "path" else "/ready"))}


def wait_for_fault(cluster, pod, scenario, seconds=90):
    needle = {"port": "connection refused", "path": "statuscode: 404", "dependency": "statuscode: 503"}[scenario]
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


def supporting_log_options(bundle, scenario):
    needles = {"port": ("Uvicorn running on", 'msg="starting HTTP server"', "INFO starting HTTP server address="),
               "path": ("Readiness route registered:", "readiness_path="),
               "dependency": ("Readiness dependency inventory unavailable", 'msg="dependency check failed"',
                              "ERROR dependency check failed dependency=")}[scenario]
    return [[o.id] for o in bundle.observations if o.kind == "app_log"
            and any(needle in o.text for needle in needles)]


def record(cluster, output, create_cluster):
    preflight()
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    status = {"status": "RECORDING", "origin": "local-kind", "started_utc": datetime.now(timezone.utc).isoformat(),
              "frameworks": ["uvicorn", "go"], "cases": [], "cluster_created": False}
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
        for framework in ("uvicorn", "go"):
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
        for framework in ("uvicorn", "go"):
            for scenario in SCENARIOS:
                case_id = f"R{len(status['cases']) + 1:03d}"
                doc = case_document(framework, scenario)
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
                bundle = collect("kind-" + cluster, NAMESPACE, name, "api")
                ids = (["status"] if scenario == "healthy" else ["events", "logs"] if scenario == "dependency"
                       else ["probe", "events", "startup"])
                if not set(ids) <= {o.id for o in bundle.observations}:
                    raise ValueError("Required recording evidence is missing; inspect collector limitations")
                label = {"cause": {"healthy": "healthy", "port": "probe_port_mismatch", "path": "probe_path_mismatch",
                                   "dependency": "dependency_unavailable"}[scenario],
                         "required_evidence_ids": ids, "split": "dev", "origin": "local-kind-recorded",
                         "framework": framework, "scenario": scenario}
                if scenario != "healthy":
                    options = supporting_log_options(bundle, scenario)
                    if not options:
                        raise ValueError("Cause-supporting application evidence is absent")
                    label["required_evidence_ids"] = ["events"] if scenario == "dependency" else ["probe", "events"]
                    label["evidence_options"] = options
                (output / "evidence" / f"{case_id}.json").write_text(json.dumps(bundle.to_dict(), indent=2) + "\n", encoding="utf-8")
                (output / "labels" / f"{case_id}.json").write_text(json.dumps(label, indent=2) + "\n", encoding="utf-8")
                status["cases"].append({"id": case_id, "framework": framework, "scenario": scenario,
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
                record(args.cluster, args.output, args.create_cluster)
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
