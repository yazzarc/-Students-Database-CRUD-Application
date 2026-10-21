"""Exercise the live HTTP API and optionally save an actual response transcript."""

import argparse
import json
from pathlib import Path
from uuid import uuid4

import httpx


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    transcript = []
    payload = {"name": "Live Demo Student", "date_of_birth": "2006-04-12",
               "email": f"live.demo.{uuid4().hex[:10]}@example.com", "course": "Python",
               "enrollment_date": "2026-01-10"}
    path = None
    with httpx.Client(base_url=args.base_url, timeout=20, trust_env=False) as client:
        def request(method, route, expected, **kwargs):
            response = client.request(method, route, **kwargs)
            entry = {"method": method, "path": route, "request": kwargs.get("json"),
                     "status": response.status_code, "response": response.json() if response.content else None}
            transcript.append(entry)
            if response.status_code != expected:
                raise RuntimeError(f"Expected {expected}, got {response.status_code}: {response.text}")
            print(f"PASS {method:6} {route:30} -> {response.status_code}")
            return entry["response"]
        try:
            request("GET", "/health", 200)
            saved = request("POST", "/students", 201, json=payload)
            path = f"/students/{saved['student_id']}"
            request("GET", path, 200)
            request("GET", "/students?course=Python&limit=2", 200)
            request("PATCH", path, 200, json={"course": "Data Science"})
            request("PUT", path, 200, json={**payload, "name": "Updated Demo Student"})
            request("POST", "/students", 409, json=payload)
            request("POST", "/students", 422, json={**payload, "date_of_birth": "invalid"})
            request("POST", "/ask", 200, json={"question": "How many students are there?"})
            request("DELETE", path, 204)
            request("GET", path, 404)
            path = None
        finally:
            if path is not None:
                client.delete(path)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(transcript, indent=2) + "\n", encoding="utf-8")
        print(f"Saved actual responses to {args.output}")
    print("Live API demonstration completed successfully.")


if __name__ == "__main__":
    main()
