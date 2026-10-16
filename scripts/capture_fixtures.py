"""Refresh the frontend's frozen API responses from the current backend and graph.

Runs the FastAPI app in-process (no server needed) against the configured FalkorDB graph and
writes ``frontend/src/mocks/``: ``decisions.json``, ``decision-details.json``, ``graph.json`` and
one ``ask-*.json`` per benchmark question. Read-only against the graph; the /ask calls use the LLM
(7 calls), so run it only when the API shape or the data changed.
"""

import json
import re
import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.main import app
from fastapi.testclient import TestClient

MOCKS = ROOT / "frontend" / "src" / "mocks"
ASK_FILES = [
    "ask-1-rabbitmq-kafka",
    "ask-2-elasticsearch-owner",
    "ask-3-redis-replacement",
    "ask-4-prometheus-decider",
    "ask-5-vault-secrets",
    "ask-6-unanswerable-quantum",
    "ask-7-unanswerable-oracle",
]


def main() -> None:
    client = TestClient(app)

    decisions = client.get("/decisions?limit=500")
    decisions.raise_for_status()
    decisions = decisions.json()
    (MOCKS / "decisions.json").write_text(json.dumps(decisions, indent=1))

    graph = client.get("/graph?limit=500").json()
    (MOCKS / "graph.json").write_text(json.dumps(graph))

    details = {
        d["id"]: client.get("/decisions/" + urllib.parse.quote(d["id"])).json() for d in decisions
    }
    (MOCKS / "decision-details.json").write_text(json.dumps(details, indent=1))
    print(f"{len(decisions)} decisions, {graph['total_nodes']} nodes, {graph['total_edges']} edges")

    mocks_ts = (ROOT / "frontend" / "src" / "api" / "mocks.ts").read_text()
    questions = re.findall(r"question: '([^']+)'", mocks_ts)
    for question, name in zip(questions, ASK_FILES, strict=True):
        response = client.post("/ask", json={"question": question})
        response.raise_for_status()
        body = response.json()
        (MOCKS / f"{name}.json").write_text(json.dumps(body, indent=2))
        print(f"{name}: primary={body.get('primary_decision_id')} citations={len(body['citations'])}")


if __name__ == "__main__":
    main()
