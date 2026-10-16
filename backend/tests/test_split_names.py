"""Tests for list-valued entity splitting and composite-node cleanup."""

import re
from typing import Any

import pytest

from app.brain import reconciliation
from app.brain.names import split_names


def test_split_names_handles_commas_and_conjunctions():
    assert split_names("Laura Croft, Fiona Gallagher, Bob Martin") == [
        "Laura Croft",
        "Fiona Gallagher",
        "Bob Martin",
    ]
    assert split_names("Snowflake, ClickHouse") == ["Snowflake", "ClickHouse"]
    assert split_names("Kevin Flynn and Laura Croft") == ["Kevin Flynn", "Laura Croft"]
    assert split_names("Alice Vance & Bob Martin; Carlos Mendez") == [
        "Alice Vance",
        "Bob Martin",
        "Carlos Mendez",
    ]


def test_split_names_leaves_single_names_and_cleans_input():
    assert split_names("Redis") == ["Redis"]
    assert split_names("System: Kafka") == ["Kafka"]
    assert split_names("  Alice Vance  ") == ["Alice Vance"]
    assert split_names("Alexander Hamilton") == ["Alexander Hamilton"]  # 'and' inside a word
    assert split_names("") == []
    assert split_names(None) == []


def test_split_names_dedupes_case_insensitively():
    assert split_names("Redis, redis, Kafka") == ["Redis", "Kafka"]


class FakeGraph:
    """Tiny in-memory stand-in that understands only the queries split_composite_nodes issues."""

    def __init__(self) -> None:
        self.nodes: dict[int, tuple[str, str]] = {}  # id -> (label, name)
        self.edges: set[tuple[int, str, int]] = set()
        self._next = 1

    def add(self, label: str, name: str) -> int:
        nid = self._next
        self._next += 1
        self.nodes[nid] = (label, name)
        return nid

    async def query(self, q: str, dataset_name: Any = None, params: dict | None = None) -> list:
        params = params or {}
        if m := re.match(r"MATCH \(n:(\w+)\) WHERE n.name IS NOT NULL RETURN id\(n\), n.name", q):
            return [[i, n] for i, (lbl, n) in self.nodes.items() if lbl == m.group(1)]
        if q.startswith("MATCH (c)-[r]->(t)"):
            return [[t, ty, {}] for s, ty, t in self.edges if s == params["cid"]]
        if q.startswith("MATCH (s)-[r]->(c)"):
            return [[s, ty, {}] for s, ty, t in self.edges if t == params["cid"]]
        if m := re.match(r"MATCH \(n:(\w+) \{name: \$name\}\) WHERE id\(n\) <> \$cid", q):
            return [
                [i]
                for i, (lbl, n) in self.nodes.items()
                if lbl == m.group(1) and n == params["name"] and i != params["cid"]
            ]
        if m := re.match(r"CREATE \(n:(\w+) \{name: \$name\}\) RETURN id\(n\)", q):
            return [[self.add(m.group(1), params["name"])]]
        if m := re.search(r"MERGE \(p\)-\[r:(\w+)\]->\(o\)", q):
            self.edges.add((params["pid"], m.group(1), params["oid"]))
            return []
        if m := re.search(r"MERGE \(o\)-\[r:(\w+)\]->\(p\)", q):
            self.edges.add((params["oid"], m.group(1), params["pid"]))
            return []
        if q.startswith("MATCH (c) WHERE id(c) = $cid DETACH DELETE c"):
            cid = params["cid"]
            self.nodes.pop(cid, None)
            self.edges = {e for e in self.edges if cid not in (e[0], e[2])}
            return []
        raise AssertionError(f"Unexpected query: {q}")


@pytest.mark.asyncio
async def test_split_composite_nodes_rewires_edges_and_removes_composite(monkeypatch):
    g = FakeGraph()
    laura = g.add("Person", "Laura Croft")
    fiona = g.add("Person", "Fiona Gallagher")
    composite = g.add("Person", "Laura Croft, Fiona Gallagher, Bob Martin")
    decision = g.add("Decision", "Decommission Snowflake")
    snowflake = g.add("System", "Snowflake")
    clickhouse = g.add("System", "ClickHouse")
    both = g.add("System", "Snowflake, ClickHouse")
    g.edges |= {
        (decision, "decided_by", composite),
        (decision, "about_system", both),
        (composite, "member_of", g.add("Team", "Data Platform")),
    }
    monkeypatch.setattr(reconciliation, "query_graph", g.query)

    result = await reconciliation.split_composite_nodes("ds")

    names = {n for _, n in g.nodes.values()}
    assert "Laura Croft, Fiona Gallagher, Bob Martin" not in names
    assert "Snowflake, ClickHouse" not in names
    bob = next(i for i, (lbl, n) in g.nodes.items() if n == "Bob Martin")
    assert [c["name"] for c in result["created"]] == ["Bob Martin"]

    for person in (laura, fiona, bob):
        assert (decision, "decided_by", person) in g.edges
    for system in (snowflake, clickhouse):
        assert (decision, "about_system", system) in g.edges
    team = next(i for i, (lbl, _) in g.nodes.items() if lbl == "Team")
    assert (laura, "member_of", team) in g.edges
    assert len(result["split"]) == 2


@pytest.mark.asyncio
async def test_split_composite_nodes_is_idempotent(monkeypatch):
    g = FakeGraph()
    g.add("Person", "Alice Vance")
    g.add("System", "Kafka")
    monkeypatch.setattr(reconciliation, "query_graph", g.query)

    before = (dict(g.nodes), set(g.edges))
    result = await reconciliation.split_composite_nodes("ds")

    assert result == {"split": [], "created": []}
    assert (g.nodes, g.edges) == before
