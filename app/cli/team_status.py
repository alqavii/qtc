from __future__ import annotations
import argparse
import requests


def main() -> None:
    p = argparse.ArgumentParser(description="Query team status over HTTP API")
    p.add_argument("--host", default="http://127.0.0.1:8000", help="API host base URL")
    p.add_argument("--team", required=True, help="Team ID")
    p.add_argument("--key", required=True, help="Team API key")
    args = p.parse_args()

    url = f"{args.host.rstrip('/')}/api/v1/team/{args.team}"
    r = requests.get(url, params={"key": args.key}, timeout=10)
    r.raise_for_status()
    data = r.json()
    print(data)


if __name__ == "__main__":
    main()

