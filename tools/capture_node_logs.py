"""Capture actual current Node lab output; requires Node, not Docker or Kubernetes.

Three runs of the same server: dependency unreachable (503), dependency available
(200) and a readiness handler delayed past a short client timeout. Only real stdout
and stderr bytes are kept, with source and log hashes.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import time
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, build_opener

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "lab/node/server.js"
OPENER = build_opener(ProxyHandler({}))


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def status(port, path, timeout=2):
    try:
        with OPENER.open(f"http://127.0.0.1:{port}{path}", timeout=timeout) as response:
            return response.status
    except HTTPError as error:
        return error.code


def run_server(log_path, env, requests):
    port = free_port()
    with log_path.open("wb") as stream:
        process = subprocess.Popen(["node", str(SERVER)], env={**os.environ, "PORT": str(port), **env},
                                   stdout=stream, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 10
            while True:
                try:
                    if status(port, "/live") == 200:
                        break
                except (URLError, OSError):
                    pass
                if process.poll() is not None or time.monotonic() >= deadline:
                    raise ValueError("Node application did not become live")
                time.sleep(.05)
            observed = {}
            for path, timeout in requests:
                try:
                    observed[path] = status(port, path, timeout)
                except (URLError, OSError, TimeoutError):
                    observed[path] = "client-timeout"
            time.sleep(.2)
        finally:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
    return port, observed


def capture(output):
    if shutil.which("node") is None:
        raise ValueError("Node is required; no logs were fabricated")
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    dependency = subprocess.Popen(["node", str(SERVER)], env={**os.environ, "PORT": "0", "READY_PATH": "/health",
                                  "DEPENDENCY_URL": "http://127.0.0.1:9/health"},
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        # The dependency role is simulated by a second instance whose /live answers 200.
        line = ""
        while "server listening on" not in line:
            line = dependency.stdout.readline()
            if not line:
                raise ValueError("Dependency instance did not start")
        dependency_port = int(line.rsplit(":", 1)[1])
        with socket.socket() as unavailable:
            unavailable.bind(("127.0.0.1", 0))
            dead_port = unavailable.getsockname()[1]
            runs = {
                "dependency-down": ({"DEPENDENCY_URL": f"http://127.0.0.1:{dead_port}/health"},
                                    [("/live", 2), ("/ready", 2), ("/unknown", 2)],
                                    {"/live": 200, "/ready": 503, "/unknown": 404}),
                "dependency-up": ({"DEPENDENCY_URL": f"http://127.0.0.1:{dependency_port}/live"},
                                  [("/live", 2), ("/ready", 2)], {"/live": 200, "/ready": 200}),
                "ready-delay": ({"DEPENDENCY_URL": f"http://127.0.0.1:{dependency_port}/live",
                                 "READY_DELAY_SECONDS": "3"},
                                [("/live", 2), ("/ready", 1)], {"/live": 200, "/ready": "client-timeout"}),
            }
            for name, (env, requests, expected) in runs.items():
                log_path = output / f"node-{name}.log"
                port, observed = run_server(log_path, env, requests)
                if observed != expected:
                    raise ValueError(f"Unexpected real Node HTTP behaviour in {name}: {observed}")
                provenance = {"status": "RECORDED", "origin": "native-node-process", "run": name, "port": port,
                              "env": env, "observed_http_status": observed,
                              "source_sha256": hashlib.sha256(SERVER.read_bytes()).hexdigest(),
                              "log_sha256": hashlib.sha256(log_path.read_bytes()).hexdigest(),
                              "node_version": subprocess.check_output(["node", "--version"], text=True).strip()}
                (output / f"node-{name}.provenance.json").write_text(json.dumps(provenance, indent=2) + "\n",
                                                                     encoding="utf-8")
                print("Recorded actual Node logs in", log_path)
    finally:
        dependency.terminate()
        dependency.wait(timeout=3)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    capture(parser.parse_args().output)
