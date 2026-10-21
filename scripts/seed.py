"""Add fictional examples through the running API; existing emails are skipped."""

import argparse
import json
from pathlib import Path

import httpx


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    records = json.loads((Path(__file__).resolve().parent.parent / "examples" / "students.json").read_text())
    with httpx.Client(base_url=args.base_url, timeout=15, trust_env=False) as client:
        for record in records:
            check = client.get("/students", params={"email": record["email"]})
            check.raise_for_status()
            if check.json()["total"]:
                print(f"Skipped existing sample: {record['name']}")
                continue
            response = client.post("/students", json=record)
            response.raise_for_status()
            print(f"Created #{response.json()['student_id']}: {record['name']}")


if __name__ == "__main__":
    main()
