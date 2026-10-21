"""Verify real HTTP CRUD and process-restart persistence using an isolated DB.

Run from the project root: python -m scripts.verify_live
No running API server is required; this script starts and stops its own server.
"""

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent


def main():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    base_url = f"http://127.0.0.1:{port}"
    with tempfile.TemporaryDirectory(prefix="ewb-live-") as directory:
        env = {**os.environ, "STUDENT_DB_PATH": str(Path(directory) / "students.db"), "OLLAMA_ENABLED": "0"}
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        log = open(Path(directory) / "server.log", "w", encoding="utf-8")
        process = None

        def start():
            nonlocal process
            process = subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
                cwd=ROOT, env=env, stdout=log, stderr=log, creationflags=flags,
            )
            with httpx.Client(timeout=1, trust_env=False) as client:
                for _ in range(100):
                    if process.poll() is not None:
                        raise RuntimeError("API process exited during startup")
                    try:
                        if client.get(base_url + "/health").status_code == 200:
                            return
                    except httpx.HTTPError:
                        pass
                    time.sleep(0.1)
            raise RuntimeError("API startup timed out")

        def stop():
            nonlocal process
            if process is not None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
                process = None

        try:
            start()
            subprocess.run([sys.executable, "-m", "scripts.demo", "--base-url", base_url,
                            "--output", str(ROOT / "docs" / "live-demo.json")], cwd=ROOT, check=True, creationflags=flags)
            with httpx.Client(base_url=base_url, trust_env=False) as client:
                response = client.post("/students", json={"name": "Persistence Demo", "date_of_birth": "2005-01-01",
                                                        "email": "persistence.demo@example.com", "course": "Python"})
                response.raise_for_status()
                saved = response.json()
            stop()
            start()
            path = f"/students/{saved['student_id']}"
            with httpx.Client(base_url=base_url, trust_env=False) as client:
                assert client.get(path).json() == saved, "Created record did not persist"
                response = client.patch(path, json={"course": "Persisted update"})
                response.raise_for_status()
                updated = response.json()
            stop()
            start()
            with httpx.Client(base_url=base_url, trust_env=False) as client:
                assert client.get(path).json() == updated, "Update did not persist"
                assert client.delete(path).status_code == 204
            stop()
            start()
            with httpx.Client(base_url=base_url, trust_env=False) as client:
                assert client.get(path).status_code == 404, "Deletion did not persist"
                assert client.get("/students").json()["total"] == 0
            print("PASS process restart: create, update and delete persisted across 4 server processes.")
            evidence = {"result": "passed", "server_processes": 4, "checks": ["live HTTP CRUD", "validation 422", "duplicate 409",
                        "missing record 404", "create persists", "update persists", "delete persists"],
                        "python": sys.version.split()[0], "database": "isolated temporary SQLite database"}
            (ROOT / "docs" / "live-verification.json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
        finally:
            stop()
            log.close()


if __name__ == "__main__":
    main()
