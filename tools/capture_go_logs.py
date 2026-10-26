"""Capture actual current Go process output; requires Go, not Docker or Kubernetes."""
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


def capture(output):
    if shutil.which("go") is None:
        raise ValueError("Go is required; no logs were fabricated")
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    binary = output / ("server.exe" if os.name == "nt" else "server")
    subprocess.run(["go", "build", "-o", str(binary), "."], cwd=ROOT / "lab/go", check=True, timeout=180)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    # Reserve a bound, non-listening port so the dependency connection really fails.
    with socket.socket() as unavailable:
        unavailable.bind(("127.0.0.1", 0))
        dependency_port = unavailable.getsockname()[1]
        env = {**os.environ, "PORT": str(port), "ROLE": "api", "READY_PATH": "/ready",
               "DEPENDENCY_URL": f"http://127.0.0.1:{dependency_port}/health"}
        opener = build_opener(ProxyHandler({}))
        def status(path):
            try:
                with opener.open(f"http://127.0.0.1:{port}{path}", timeout=2) as response:
                    return response.status
            except HTTPError as error:
                return error.code
        log_path = output / "server.log"
        with log_path.open("wb") as stream:
            process = subprocess.Popen([str(binary)], env=env, stdout=stream, stderr=subprocess.STDOUT)
            try:
                deadline = time.monotonic() + 10
                while True:
                    try:
                        if status("/live") == 200:
                            break
                    except (URLError, OSError):
                        pass
                    if process.poll() is not None or time.monotonic() >= deadline:
                        raise ValueError("Compiled Go application did not become live")
                    time.sleep(.05)
                observed = {"/live": status("/live"), "/ready": status("/ready"), "/unknown": status("/unknown")}
                if observed != {"/live": 200, "/ready": 503, "/unknown": 404}:
                    raise ValueError("Unexpected real Go HTTP behavior")
            finally:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
    provenance = {"status": "RECORDED", "origin": "native-go-process", "port": port,
                  "observed_http_status": observed,
                  "source_sha256": hashlib.sha256((ROOT / "lab/go/main.go").read_bytes()).hexdigest(),
                  "log_sha256": hashlib.sha256(log_path.read_bytes()).hexdigest(),
                  "go_version": subprocess.check_output(["go", "version"], text=True).strip()}
    (output / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    print("Recorded actual Go logs in", output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    capture(args.output)
