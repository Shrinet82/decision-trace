"""Create (or re-create) the showcase organization "Arachne (real GitHub ADRs)".

It is a sample organization: visible to everyone in the organization menu, read-only apart from
tagged demo ingests that reset themselves, never deleted automatically. Its data is the ADR log of
a real open-source repository, imported with the same GitHub importer anyone can use in their own
organization. After the import everything is un-tagged, so the automatic demo reset never removes it.

    PYTHONPATH=backend python scripts/create_showcase_org.py            # create
    PYTHONPATH=backend python scripts/create_showcase_org.py --recreate  # delete the old graph first

Touches only the showcase organization's own graphs and its registry record.
"""

import argparse
import asyncio
import json

from app.brain import orgctx
from app.brain.memory import delete_graph, query_graph, run_on_graph
from app.config import get_settings
from app.ingest.github import GithubRequest, run_github_import
from app.ingest.live import changes_graph_name
from app.orgs import registry

ORG_ID = "arachne"
ORG_NAME = "Arachne (real GitHub ADRs)"
REPO = "https://github.com/arachne-framework/architecture"


async def main(recreate: bool) -> None:
    await registry.load(force=True)
    existing = registry._orgs.get(ORG_ID)
    if existing:
        if not recreate:
            raise SystemExit(f"{ORG_ID} already exists; pass --recreate to replace it")
        await delete_graph(existing["graph_name"])
        await delete_graph(changes_graph_name(existing["graph_name"]))
        await run_on_graph(registry.REGISTRY_GRAPH, "MATCH (o:Org {id: $id}) DELETE o", {"id": ORG_ID})
        registry._orgs.pop(ORG_ID, None)
    org, _ = await registry.create(ORG_NAME, sample=True, slug=ORG_ID)
    print("created", org["id"], org["graph_name"])

    dataset = get_settings().DATASET_NAME
    stats = None
    with orgctx.org_scope(org["id"], org["graph_name"], sample=True):
        async for event in run_github_import(GithubRequest(repo_url=REPO, include_prs=True), dataset):
            if event["event"] == "progress":
                print(" ", event["data"]["phase"], event["data"]["status"], event["data"].get("detail", ""))
            elif event["event"] == "error":
                raise SystemExit(f"import failed: {event['data']['message']}")
            elif event["event"] == "diff":
                stats = event["data"].get("import")
        # Make the data permanent: the automatic demo reset only removes tagged items
        await query_graph("MATCH (n) WHERE n.demo_ingest_id IS NOT NULL SET n.demo_ingest_id = NULL", dataset_name=dataset)
        await query_graph("MATCH ()-[r]->() WHERE r.demo_ingest_id IS NOT NULL SET r.demo_ingest_id = NULL", dataset_name=dataset)
        nodes = (await query_graph("MATCH (n) RETURN count(n)", dataset_name=dataset))[0][0]
        edges = (await query_graph("MATCH ()-[r]->() RETURN count(r)", dataset_name=dataset))[0][0]
        tagged = (await query_graph("MATCH (n) WHERE n.demo_ingest_id IS NOT NULL RETURN count(n)", dataset_name=dataset))[0][0]
    # The import's change-log entry would let a reset "revert" it; the showcase has no history to undo
    await delete_graph(changes_graph_name(org["graph_name"]))
    await registry.set_source_count(org["id"], int((stats or {}).get("adrs", 0)))
    print(json.dumps({"nodes": nodes, "edges": edges, "still_tagged": tagged, "import": stats}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--recreate", action="store_true")
    asyncio.run(main(parser.parse_args().recreate))
