"""CLI with explicit gates for cluster reads and chargeable model requests."""
import argparse
import json
from pathlib import Path
import sys

from .baseline import diagnose
from .collector import collect
from .evaluation import evaluate, fingerprint, digest
from .llm import ModelClient
from .models import load_bundle


def write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Read-only readiness diagnosis and offline replay")
    sub = parser.add_subparsers(dest="command", required=True)
    one = sub.add_parser("diagnose")
    one.add_argument("bundle")
    one.add_argument("--variant", choices=("A1", "C1", "H"), default="A1")
    one.add_argument("--allow-model-calls", action="store_true")
    ev = sub.add_parser("evaluate")
    ev.add_argument("--cases", default="data/dev")
    ev.add_argument("--output", required=True)
    ev.add_argument("--variants", default="A1")
    ev.add_argument("--allow-model-calls", action="store_true")
    ev.add_argument("--manifest")
    freeze = sub.add_parser("freeze")
    freeze.add_argument("--cases", default="data/dev")
    freeze.add_argument("--output", required=True)
    freeze.add_argument("--include-model-config", action="store_true")
    live = sub.add_parser("collect")
    for key in ("context", "namespace", "pod", "container", "output"):
        live.add_argument("--" + key, required=True)
    live.add_argument("--allow-cluster-read", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "collect":
            if not args.allow_cluster_read:
                raise ValueError("Use --allow-cluster-read to read the explicitly selected cluster")
            result = collect(args.context, args.namespace, args.pod, args.container)
            write_new(args.output, result.to_dict())
        elif args.command == "freeze":
            config = None
            if args.include_model_config:
                c = ModelClient.from_env()
                config = {"provider": c.provider, "model": c.model, "api_version": c.api_version,
                          "endpoint_sha256": digest(c.endpoint.encode()), "temperature": 0, "max_tokens": 700}
            write_new(args.output, fingerprint(Path(args.cases), config))
        else:
            variants = args.variants.split(",") if args.command == "evaluate" else [args.variant]
            client = None
            if set(variants) - {"A1"}:
                if not args.allow_model_calls:
                    raise ValueError("Use --allow-model-calls for chargeable provider requests")
                client = ModelClient.from_env()
            if args.command == "evaluate":
                result = evaluate(args.cases, args.output, variants, client, args.manifest)
                print(json.dumps(result, indent=2))
                return 1 if any(x["errors"] for x in result["variants"].values()) else 0
            bundle = load_bundle(args.bundle)
            result = diagnose(bundle) if args.variant in ("A1", "H") else None
            if result is None or (args.variant == "H" and result.cause == "insufficient_evidence"):
                result, _ = client.diagnose(bundle)
            print(json.dumps(result.to_dict(), indent=2))
        return 0
    except (ValueError, OSError, KeyError):
        print("Operation failed: check arguments, evidence schema, permissions and provider configuration. Existing outputs are never overwritten.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
