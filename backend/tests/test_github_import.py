"""GitHub import: URL parsing, finding ADRs, reading them deterministically, supersession, the run."""

from unittest.mock import patch

import pytest

from app.ingest import github
from app.ingest.github import (
    GithubError,
    GithubRequest,
    is_decision_item,
    parse_adr,
    parse_repo_url,
    select_adr_paths,
    supersession_pairs,
)

NYGARD_5 = """# 5. Use Kafka for events

Date: 2026-02-10

## Status

Accepted

Supersedes [3. Use RabbitMQ](0003-use-rabbitmq.md)

## Context
We need a replayable log.

## Decision
We will use Kafka for all event messaging.

## Consequences
Operate a Kafka cluster.
"""

NYGARD_3 = """# 3. Use RabbitMQ

Date: 2025-06-01

## Status

Superseded by [5. Use Kafka for events](0005-use-kafka.md)

## Decision
We will use RabbitMQ for queues.
"""

MADR = """---
status: "accepted"
date: 2026-03-04
deciders: Ana Lopez, Raj Patel
---
# Use PostgreSQL for billing

## Decision Outcome
Chosen option: "PostgreSQL", because invoices need transactions.
"""


def test_repo_urls():
    assert parse_repo_url("https://github.com/backstage/backstage") == ("backstage", "backstage")
    assert parse_repo_url("github.com/adr/madr.git") == ("adr", "madr")
    assert parse_repo_url("https://github.com/o/r/tree/main/docs?x=1") == ("o", "r")
    for bad in ["https://gitlab.com/o/r", "https://github.com/onlyowner", "https://github.com/../x"]:
        with pytest.raises(GithubError):
            parse_repo_url(bad)


def test_adr_paths_come_from_decision_folders_and_adr_names():
    paths = [
        "README.md", "docs/adr/0001-record.md", "docs/adr/README.md", "docs/adr/template.md", "doc/adr/0002-x.md",
        "docs/decisions/0003-y.md", "architecture/decisions/ADR-12-z.md", "src/app.py", "adr/0004-q.md",
        "docs/guide.md", "notes/ADR-7-late.md", "node_modules/pkg/docs/adr/0001.md", "docs/adr/index.md",
    ]
    got = select_adr_paths(paths)
    assert set(got) == {
        "docs/adr/0001-record.md", "doc/adr/0002-x.md", "docs/decisions/0003-y.md",
        "architecture/decisions/ADR-12-z.md", "adr/0004-q.md", "notes/ADR-7-late.md",
    }
    assert len(select_adr_paths([f"docs/adr/{i:04d}-a.md" for i in range(100)])) == 40


def test_nygard_adr_with_supersedes_link():
    a = parse_adr("docs/adr/0005-use-kafka.md", NYGARD_5)
    assert (a.number, a.title, a.status, a.date) == (5, "Use Kafka for events", "accepted", "2026-02-10")
    assert a.supersedes == [3] and a.superseded_by == []
    assert a.quote == "We will use Kafka for all event messaging."


def test_superseded_status_and_back_reference():
    a = parse_adr("docs/adr/0003-use-rabbitmq.md", NYGARD_3)
    assert a.status == "superseded" and a.superseded_by == [5] and a.supersedes == []


def test_madr_front_matter():
    a = parse_adr("docs/decisions/0007-postgres.md", MADR)
    assert a.number == 7 and a.title == "Use PostgreSQL for billing" and a.status == "accepted"
    assert a.date == "2026-03-04" and a.deciders == ["Ana Lopez", "Raj Patel"]
    assert a.quote.startswith('Chosen option: "PostgreSQL"')


def test_supersession_is_taken_from_either_side_without_duplicates():
    five = parse_adr("0005-use-kafka.md", NYGARD_5)
    three = parse_adr("0003-use-rabbitmq.md", NYGARD_3)
    pairs = supersession_pairs([three, five])
    assert [(n.number, o.number) for n, o, _ in pairs] == [(5, 3)]
    # a reference to an ADR that is not in the repository is ignored
    lone = parse_adr("0009-x.md", "# 9. X\n\n## Status\n\nAccepted\n\nSupersedes ADR-2\n\n## Decision\nWe will do the thing today.")
    assert supersession_pairs([lone]) == []


def test_decision_like_items():
    assert is_decision_item("RFC: new cache layer", [], "")
    assert is_decision_item("Cache", ["decision"], "")
    assert is_decision_item("Cache", [], "We decided to drop Redis.")
    assert not is_decision_item("Fix typo", ["bug"], "Typo in README")


class FakeClient:
    authenticated = False
    remaining = 50

    async def close(self):
        pass

    async def api(self, path, /, **params):
        if path.endswith("/git/trees/main"):
            return {"tree": [{"type": "blob", "path": "docs/adr/0003-use-rabbitmq.md"}, {"type": "blob", "path": "docs/adr/0005-use-kafka.md"}, {"type": "blob", "path": "src/x.py"}]}
        if path.endswith("/commits"):
            return [{"commit": {"author": {"date": "2026-01-02T00:00:00Z", "name": "Casey Author"}}}]
        if path.endswith("/pulls"):
            return [{"number": 12, "title": "RFC: adopt Vault", "body": "We decided to adopt Vault for secrets.", "labels": [], "user": {"login": "dana"}, "assignees": [], "merged_at": "2026-05-01T10:00:00Z", "html_url": "https://github.com/o/r/pull/12"}]
        if path.endswith("/issues"):
            return []
        return {"default_branch": "main", "private": False, "html_url": "https://github.com/o/r", "description": "d", "pushed_at": "2026-09-01T00:00:00Z"}

    async def raw(self, owner, repo, ref, path):
        return {"docs/adr/0003-use-rabbitmq.md": NYGARD_3 + "x" * 80, "docs/adr/0005-use-kafka.md": NYGARD_5}[path]


async def _run(client=None):
    queries: list[tuple[str, dict]] = []

    async def fake_query(q, dataset_name=None, params=None):
        queries.append((q, params or {}))
        return []

    async def fake_state(dataset):
        return {"health": {}, "orphans": set(), "codes": {}}

    async def fake_llm(prompt, text, model, max_tokens):
        if model is github.AdrSystems:
            return github.AdrSystems(systems=["Kafka"])
        return github.ItemJudgement(is_decision=True, title="Adopt Vault", decided_by="Dana Whitfield", system="Vault", status="accepted", quote="We decided to adopt Vault for secrets.")

    async def noop(*a, **k):
        return None

    with patch.object(github, "query_graph", fake_query), patch.object(github, "_snapshot_state", fake_state), \
            patch.object(github, "_llm", fake_llm), patch.object(github, "record_change", noop), patch.object(github, "rollback", noop):
        events = [e async for e in github.run_github_import(GithubRequest(repo_url="https://github.com/o/r"), "ds", client or FakeClient())]
    return events, queries


async def test_the_import_writes_adrs_prs_and_supersession():
    events, queries = await _run()
    assert events[-1]["event"] == "diff", events[-1]
    diff = events[-1]["data"]
    assert diff["import"]["adrs"] == 2 and diff["import"]["items_decisions"] == 1 and diff["import"]["supersedes"] == 1
    assert [e["data"]["phase"] for e in events if e["event"] == "progress"][:2] == ["fetching", "fetching"]
    text = "\n".join(q for q, _ in queries)
    assert "CREATE (n:Decision)" in text and "CREATE (a)-[x:supersedes]->(b)" in text and "CREATE (a)-[x:decided_by]->(b)" in text
    decisions = next(p["rows"] for q, p in queries if "CREATE (n:Decision)" in q)
    assert len(decisions) == 3 and {d["status"] for d in decisions} == {"accepted"}
    people = next(p["rows"] for q, p in queries if "CREATE (n:Person)" in q)
    assert {p["name"] for p in people} == {"Dana Whitfield"}
    assert all(r["props"]["demo_ingest_id"] for q, p in queries if "[x:supersedes]" in q for r in p["rows"])


async def test_a_repository_already_imported_is_refused():
    async def exists(q, dataset_name=None, params=None):
        return [[1]] if "Project" in q else []

    with patch.object(github, "query_graph", exists):
        events = [e async for e in github.run_github_import(GithubRequest(repo_url="https://github.com/o/r"), "ds", FakeClient())]
    assert events[-1]["event"] == "error" and "already been imported" in events[-1]["data"]["message"]


async def test_a_repository_without_adrs_says_where_it_looked():
    class Empty(FakeClient):
        async def api(self, path, /, **params):
            if "/git/trees" in path:
                return {"tree": [{"type": "blob", "path": "src/x.py"}]}
            if path.endswith(("/pulls", "/issues")):
                return []
            return await super().api(path, **params)

    async def none(q, dataset_name=None, params=None):
        return []

    with patch.object(github, "query_graph", none):
        events = [e async for e in github.run_github_import(GithubRequest(repo_url="https://github.com/o/r"), "ds", Empty())]
    assert events[-1]["event"] == "error" and "docs/adr" in events[-1]["data"]["message"]


async def test_rate_limit_and_missing_repos_have_clear_messages():
    class Limited(FakeClient):
        async def api(self, path, /, **params):
            raise GithubError("GitHub's API rate limit has been reached. Unauthenticated requests are limited to 60 per hour. Try again later.")

    events = [e async for e in github.run_github_import(GithubRequest(repo_url="https://github.com/o/r"), "ds", Limited())]
    assert "rate limit" in events[-1]["data"]["message"]
    events = [e async for e in github.run_github_import(GithubRequest(repo_url="https://example.com/o/r"), "ds", FakeClient())]
    assert "github.com" in events[-1]["data"]["message"]


def test_the_endpoint_is_closed_to_the_sample_organization():
    from fastapi.testclient import TestClient

    from app.server import app

    res = TestClient(app).post("/ingest/github", json={"repo_url": "https://github.com/o/r"})
    assert res.status_code == 403 and "organizations you create" in res.json()["detail"]


def test_titles_come_from_front_matter_then_h1_then_the_file_name():
    fm = parse_adr("docs/adr/adr013-use-node-fetch.md", "---\ntitle: 'ADR013: Use node-fetch for backend requests'\n---\n## Context\nx\n## Decision\nWe use node-fetch for all requests.\n")
    assert fm.title == "Use node-fetch for backend requests" and fm.number == 13
    nameless = parse_adr("docs/adr/adr014-use-cache-layer.md", "## Context\nSome words here.\n\n## Decision\nWe will use a cache layer for lookups.\n")
    assert nameless.title == "Use cache layer" and nameless.number == 14


def test_a_record_prefix_is_not_part_of_the_title():
    a = parse_adr("adr-004-persistent-configuration.md", "# Architecture Decision Record: Persistent Configuration\n\n## Status\n\nProposed\n\n## Decision\nWe will store configuration in Datomic always.\n")
    assert a.title == "Persistent Configuration"
