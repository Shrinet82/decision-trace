"""Organizations: one graph each, selected by the /orgs/<id>/ path prefix."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.api import orgs as orgs_api
from app.brain import cache, orgctx
from app.brain.memory import resolve_active_graph_name
from app.orgs import registry
from app.server import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def fresh_registry(monkeypatch):
    registry._orgs.clear()
    registry._touched.clear()
    registry._loaded = True  # nothing to read from FalkorDB in unit tests
    orgs_api._creates.clear()
    calls: list[tuple[str, str]] = []

    async def fake_run(graph, query, params=None):
        calls.append((graph, query))
        return []

    deleted: list[str] = []

    async def fake_delete(graph):
        deleted.append(graph)
        return True

    monkeypatch.setattr(registry, "run_on_graph", fake_run)
    monkeypatch.setattr(registry, "delete_graph", fake_delete)
    monkeypatch.setattr(orgs_api, "run_on_graph", fake_run)
    return {"calls": calls, "deleted": deleted}


def _create(name="Acme Labs"):
    return client.post("/orgs", json={"name": name})


def test_create_returns_an_id_and_never_the_graph_name(fresh_registry):
    res = _create()
    assert res.status_code == 201
    body = res.json()
    assert body["owner_key"].startswith("ok_") and body["owner_key"] not in str(registry._orgs)
    assert body["name"] == "Acme Labs" and body["sample"] is False
    assert body["id"].startswith("acme-labs-") and "graph_name" not in body
    assert registry._orgs[body["id"]]["graph_name"].startswith("org_acme_labs_")
    graphs = {g for g, _ in fresh_registry["calls"]}
    assert registry._orgs[body["id"]]["graph_name"] in graphs and registry.REGISTRY_GRAPH in graphs


@pytest.mark.parametrize("name", ["", "   ", "x" * 41, "bad\x00name"])
def test_bad_names_are_rejected(name):
    assert _create(name).status_code == 422


def test_creation_is_limited_to_three_per_hour_per_ip():
    for _ in range(3):
        assert _create().status_code == 201
    res = _create()
    assert res.status_code == 429 and "per hour" in res.json()["detail"]


def test_the_total_number_of_organizations_is_capped(monkeypatch):
    monkeypatch.setattr(registry, "MAX_USER_ORGS", 2)
    monkeypatch.setattr(orgs_api, "MAX_CREATES_PER_HOUR", 100)
    assert _create("One").status_code == 201
    assert _create("Two").status_code == 201
    res = _create("Three")
    assert res.status_code == 409 and "full" in res.json()["detail"]


def test_unknown_organization_is_404_under_any_path():
    assert client.get("/orgs/nope-123456").status_code == 404
    res = client.get("/orgs/nope-123456/decisions")
    assert res.status_code == 404 and "does not exist" in res.json()["detail"]


def test_delete_removes_both_graphs_and_the_record(fresh_registry):
    org = _create().json()
    graph = registry._orgs[org["id"]]["graph_name"]
    assert client.delete(f"/orgs/{org['id']}", headers={"X-Org-Key": org["owner_key"]}).json() == {"deleted": org["id"]}
    assert fresh_registry["deleted"] == [graph, f"{graph}__changes"]
    assert org["id"] not in registry._orgs
    assert client.get(f"/orgs/{org['id']}").status_code == 404
    assert client.delete(f"/orgs/{org['id']}", headers={"X-Org-Key": org["owner_key"]}).status_code == 404


def test_the_sample_organization_cannot_be_deleted():
    assert client.delete("/orgs/sample").status_code == 403


def test_reset_is_refused_inside_a_user_organization():
    org = _create().json()
    res = client.post(f"/orgs/{org['id']}/ingest/reset")
    assert res.status_code == 403 and "keep their data" in res.json()["detail"]


async def test_the_prefix_selects_the_graph_and_the_default_stays_the_sample():
    org, _ = await registry.create("Scoped")
    sample_graph = await resolve_active_graph_name()
    assert orgctx.current_graph() is None
    with orgctx.org_scope(org["id"], org["graph_name"]):
        assert await resolve_active_graph_name() == org["graph_name"]
        # an explicit graph name (the activity log) still resolves as itself
        assert orgctx.current_graph() == org["graph_name"]
    assert await resolve_active_graph_name() == sample_graph


async def test_caches_are_kept_per_organization():
    calls = []

    async def compute():
        calls.append(orgctx.scope())
        return orgctx.scope()

    assert await cache.cached("ns", "k", 60, compute) == ""
    with orgctx.org_scope("a", "graph_a"):
        assert await cache.cached("ns", "k", 60, compute) == "graph_a"
    with orgctx.org_scope("b", "graph_b"):
        assert await cache.cached("ns", "k", 60, compute) == "graph_b"
    assert await cache.cached("ns", "k", 60, compute) == ""
    assert calls == ["", "graph_a", "graph_b"]


async def test_one_organizations_ingest_lock_does_not_block_another():
    from app.ingest.live import INGEST_LOCK

    with orgctx.org_scope("a", "graph_a"):
        await INGEST_LOCK.acquire()
        assert INGEST_LOCK.locked()
    with orgctx.org_scope("b", "graph_b"):
        assert not INGEST_LOCK.locked()
    assert not INGEST_LOCK.locked()
    with orgctx.org_scope("a", "graph_a"):
        INGEST_LOCK.release()
        assert not INGEST_LOCK.locked()


async def test_idle_organizations_are_deleted_but_never_the_sample(fresh_registry):
    old, _ = await registry.create("Old")
    fresh, _ = await registry.create("Fresh")
    registry._orgs[old["id"]]["last_active"] = (
        datetime.now(timezone.utc) - timedelta(hours=registry.IDLE_HOURS + 1)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")
    removed = await registry.delete_idle()
    assert removed == [old["id"]]
    assert fresh["id"] in registry._orgs
    assert (await registry.get("sample"))["sample"] is True


def test_ids_are_slugs():
    assert registry.slugify("Acme Labs!") == "acme-labs"
    assert registry.slugify("日本") == "org"
    assert len(registry.slugify("x" * 100)) <= 24


def test_deleting_needs_the_owner_key(fresh_registry):
    org = _create().json()
    assert client.delete(f"/orgs/{org['id']}").status_code == 403
    assert client.delete(f"/orgs/{org['id']}", headers={"X-Org-Key": "ok_wrong"}).status_code == 403
    assert org["id"] in registry._orgs
    assert client.delete(f"/orgs/{org['id']}", headers={"X-Org-Key": org["owner_key"]}).status_code == 200


def test_every_write_into_a_user_org_needs_the_owner_key():
    org = _create().json()
    gh = {"repo_url": "https://github.com/o/r"}
    files = {"files": [{"name": "a.md", "text": "We decided X."}]}
    paste = {"type": "meeting", "title": "t", "date": "2026-10-16", "text": "We decided X."}
    for path, body in [("ingest", paste), ("ingest/batch", files), ("ingest/github", gh)]:
        res = client.post(f"/orgs/{org['id']}/{path}", json=body)
        assert res.status_code == 403, path
        assert "owner key" in res.json()["detail"]
        res = client.post(f"/orgs/{org['id']}/{path}", json=body, headers={"X-Org-Key": "ok_wrong"})
        assert res.status_code == 403, path
    # Viewing stays open
    assert client.get(f"/orgs/{org['id']}/decisions").status_code in (200, 500)  # graph is mocked away here
    assert client.get(f"/orgs/{org['id']}/ingest/status").status_code == 200


async def test_organizations_from_before_keys_are_view_only():
    org, _ = await registry.create("Legacy")
    registry._orgs[org["id"]]["owner_hash"] = ""
    assert not registry.key_matches(registry._orgs[org["id"]], "ok_anything")
    assert not registry.key_matches(registry._orgs[org["id"]], None)


async def test_showcase_organizations_are_listed_protected_and_never_idle_deleted(fresh_registry):
    showcase, key = await registry.create("Arachne (real GitHub ADRs)", sample=True, slug="arachne")
    assert key is None and showcase["sample"] is True
    listing = client.get("/orgs").json()
    assert [o["id"] for o in listing] == ["arachne"] and "owner_key" not in listing[0]
    assert "graph_name" not in listing[0]
    assert client.delete("/orgs/arachne").status_code == 403
    assert registry.user_orgs() == [] and [o["id"] for o in registry.sample_orgs()] == ["arachne"]
    registry._orgs["arachne"]["last_active"] = "2020-01-01T00:00:00Z"
    assert await registry.delete_idle() == []
    # ingest/github stays closed in a showcase organization; reset is allowed (it clears demo data only)
    assert client.post("/orgs/arachne/ingest/github", json={"repo_url": "https://github.com/o/r"}).status_code == 403
    with orgctx.org_scope("arachne", showcase["graph_name"], sample=True):
        assert not orgctx.is_user_org()
        assert orgctx.current_graph() == showcase["graph_name"]
