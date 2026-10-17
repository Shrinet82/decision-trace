"""Refresh the frontend's frozen API responses from the current backend and graph.

Runs the FastAPI app in-process (no server needed) against the configured FalkorDB graph and
writes ``frontend/src/mocks/``: ``decisions.json``, ``decision-details.json`` (full decision pages),
``graph.json``, ``systems.json``, ``system-details.json``, ``people.json``, ``person-details.json``
``sources.json`` and ``source-details.json``, ``ask-stream.json`` (the recorded /ask/stream event
stream of every suggested and benchmark question) and one ``ask-*.json`` per benchmark question
(the final result of its stream). Read-only against the graph. The asks use the LLM (12 calls);
pass ``--no-ask`` to keep the existing ask fixtures.
"""

import json
import re
import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.server import app
from fastapi.testclient import TestClient

MOCKS = ROOT / "frontend" / "src" / "mocks"
SUGGESTED_QUESTIONS = [
    "Why did we move sessions to Keycloak?",
    "Do any decisions conflict?",
    "What's affected if we drop Snowflake?",
    "Who knows the most about Kafka?",
    "Which systems have no owner?",
]
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

    systems = client.get("/systems").json()
    (MOCKS / "systems.json").write_text(json.dumps(systems, indent=1))
    system_details = {
        s["name"]: client.get("/systems/" + urllib.parse.quote(s["name"])).json() for s in systems
    }
    (MOCKS / "system-details.json").write_text(json.dumps(system_details, indent=1))

    people = client.get("/people").json()
    (MOCKS / "people.json").write_text(json.dumps(people, indent=1))
    person_details = {
        p["name"]: client.get("/people/" + urllib.parse.quote(p["name"])).json() for p in people
    }
    (MOCKS / "person-details.json").write_text(json.dumps(person_details, indent=1))
    print(f"{len(systems)} systems, {len(people)} people")

    sources = client.get("/sources").json()
    (MOCKS / "sources.json").write_text(json.dumps(sources, indent=1))
    source_details = {
        f"{i['kind']}/{i['key']}": client.get(f"/sources/{i['kind']}/" + urllib.parse.quote(i["key"])).json()
        for i in sources["items"]
    }
    (MOCKS / "source-details.json").write_text(json.dumps(source_details))
    print(f"{len(sources['items'])} sources {sources['counts']}")

    if "--no-ask" in sys.argv:
        return

    mocks_ts = (ROOT / "frontend" / "src" / "api" / "mocks.ts").read_text()
    benchmark = re.findall(r"question: '([^']+)'", mocks_ts)
    streams: dict[str, list[dict]] = {}
    for question in SUGGESTED_QUESTIONS + benchmark:
        streams[question] = record_stream(client, question)
        done = streams[question][-1]["data"]
        print(f"{question!r}: intent={done.get('intent')} primary={done.get('primary_decision_id')} "
              f"citations={len(done.get('citations', []))} total={done.get('trace', {}).get('total_ms')}ms")
    (MOCKS / "ask-stream.json").write_text(json.dumps(streams))
    for question, name in zip(benchmark, ASK_FILES, strict=True):
        (MOCKS / f"{name}.json").write_text(json.dumps(streams[question][-1]["data"], indent=2))


def record_stream(client: TestClient, question: str) -> list[dict]:
    """POST /ask/stream and decode every server-sent event; the last one must be `done`."""
    with client.stream("POST", "/ask/stream", json={"question": question}) as response:
        response.raise_for_status()
        body = "".join(response.iter_text())
    events = []
    for frame in body.split("\n\n"):
        lines = dict(line.split(": ", 1) for line in frame.splitlines() if ": " in line)
        if "event" in lines and "data" in lines:
            events.append({"event": lines["event"], "data": json.loads(lines["data"])})
    if not events or events[-1]["event"] != "done":
        raise RuntimeError(f"Stream for {question!r} did not finish: {events[-1:]}")
    return events


if __name__ == "__main__":
    main()
