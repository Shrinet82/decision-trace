#!/usr/bin/env python3
"""FalkorDB Cloud Keepalive Script.

Executes a minimal OpenCypher query ('RETURN 1 as keepalive') against the
FalkorDB Cloud instance to maintain active state and prevent the free tier
instance from idling out or shutting down after inactivity.

Safe to run on a scheduled cron job (e.g., every 6 hours).
Reads credentials strictly from environment variables or local .env file.
"""

from datetime import datetime, timezone
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load .env if present
env_path = Path(__file__).resolve().parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)

from falkordb import FalkorDB  # noqa: E402


def run_keepalive() -> int:
    host = os.getenv("FALKORDB_HOST")
    port_str = os.getenv("FALKORDB_PORT", "6379")
    username = os.getenv("FALKORDB_USERNAME", "falkordb")
    password = os.getenv("FALKORDB_PASSWORD")
    graph_name = os.getenv("FALKORDB_GRAPH_NAME", "company_brain")

    if not host or not password:
        print(f"[{datetime.now(timezone.utc).isoformat()}] ERROR: Missing FALKORDB_HOST or FALKORDB_PASSWORD.")
        return 1

    try:
        port = int(port_str)
        db = FalkorDB(host=host, port=port, username=username, password=password)
        graph = db.select_graph(graph_name)
        result = graph.query("RETURN 1 as keepalive")
        if result and len(result.result_set) > 0:
            print(f"[{datetime.now(timezone.utc).isoformat()}] SUCCESS: FalkorDB Cloud keepalive query executed successfully.")
            return 0
        else:
            print(f"[{datetime.now(timezone.utc).isoformat()}] WARNING: Unexpected empty response from keepalive query.")
            return 1
    except Exception as exc:
        print(f"[{datetime.now(timezone.utc).isoformat()}] ERROR: FalkorDB Cloud keepalive failed: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(run_keepalive())
