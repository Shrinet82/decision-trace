"""Verification script for /ask outputs and Decision Health states.

Tests:
1. 5 core domain questions:
   - Why did we choose RabbitMQ over Kafka?
   - Who owns Elasticsearch now?
   - What replaced Redis for sessions?
   - Who decided to deploy Prometheus Operator?
   - What database secrets management policy was adopted?
2. 2 unanswerable questions (asserting 'not found' and 0 citations):
   - What is our company's policy on using quantum computing for cryptography?
   - Who authorized the migration of our core database to Oracle Cloud in 2024?
3. Decision health audit (active, superseded, contradicted, stale) + reasons.
"""

import json
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_ask_queries():
    print("=" * 70)
    print("VERIFYING /ask ON SEEDED GRAPH (5 CORE + 2 UNANSWERABLE)")
    print("=" * 70)

    core_queries = [
        "Why did we choose RabbitMQ over Kafka?",
        "Who owns Elasticsearch now?",
        "What replaced Redis for sessions?",
        "Who decided to deploy Prometheus Operator?",
        "What database secrets management policy was adopted?",
    ]

    print("\n--- 5 CORE DOMAIN QUESTIONS ---")
    for idx, q in enumerate(core_queries, 1):
        resp = client.post("/ask", json={"question": q, "dataset_name": "company_brain"})
        assert resp.status_code == 200, f"Error {resp.status_code}: {resp.text}"
        data = resp.json()
        print(f"\n[Q{idx}] {q}")
        print(f"Answer: {data['answer']}")
        print(f"Citations ({len(data['citations'])}):")
        for c in data["citations"]:
            print(f"  - [{c.get('type')}] {c.get('title')} ({c.get('source_id')})")
        gp = data.get("graph_path", {})
        nodes = gp.get("nodes", [])
        edges = gp.get("edges", [])
        print(f"Graph Path: {len(nodes)} nodes, {len(edges)} edges")
        node_labels = {n.get("label") for n in nodes}
        print(f"Node labels in path: {sorted(node_labels)}")

    unanswerable_queries = [
        "What is our company's policy on using quantum computing for cryptography?",
        "Who authorized the migration of our core database to Oracle Cloud in 2024?",
    ]

    print("\n--- 2 UNANSWERABLE QUESTIONS ---")
    for idx, q in enumerate(unanswerable_queries, 1):
        resp = client.post("/ask", json={"question": q, "dataset_name": "company_brain"})
        assert resp.status_code == 200, f"Error {resp.status_code}: {resp.text}"
        data = resp.json()
        ans = data["answer"].lower()
        citations = data["citations"]
        print(f"\n[Unanswerable Q{idx}] {q}")
        print(f"Answer: {data['answer']}")
        print(f"Citations count: {len(citations)}")
        assert (
            "not find" in ans
            or "not found" in ans
            or "no information" in ans
            or "no decisions" in ans
        ), f"Expected 'not found' response, got: {data['answer']}"
        assert len(citations) == 0, f"Expected 0 invented citations, got {len(citations)}"
        print("  -> Passed: Refused correctly with 0 citations.")


def test_decision_health():
    print("\n" + "=" * 70)
    print("VERIFYING DECISION HEALTH AUDIT (/decisions)")
    print("=" * 70)

    resp = client.get("/decisions?dataset_name=company_brain")
    assert resp.status_code == 200, f"Error: {resp.text}"
    decisions = resp.json()

    health_counts = {"active": 0, "superseded": 0, "contradicted": 0, "stale": 0}
    for d in decisions:
        h = d.get("health", "active")
        health_counts[h] = health_counts.get(h, 0) + 1
        print(f"- [{d['id']}] {d['title']}")
        print(f"    Health: {h} | Decider: {d.get('decided_by')} | System: {d.get('system')}")
        print(f"    Reason: {d.get('health_reason')}")

    print("\nDECISION HEALTH SUMMARY:")
    for status, count in health_counts.items():
        print(f"  * {status.upper()}: {count}")


if __name__ == "__main__":
    test_ask_queries()
    test_decision_health()
