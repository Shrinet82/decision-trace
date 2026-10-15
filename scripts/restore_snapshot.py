"""Restore FalkorDB Company Brain graph from a stored JSON snapshot.

Enables instant restoration of the validated knowledge graph for demos,
integration tests, and benchmarks without requiring any LLM API calls.
"""

import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.brain.memory import (
    get_falkordb_memory_usage,
    get_or_create_dataset_graph_name,
    query_graph,
    reset,
)
from app.config import get_settings

logger = logging.getLogger("restore_snapshot")
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)

SNAPSHOT_DIR = Path(__file__).resolve().parent.parent / "data" / "snapshot"
DEFAULT_SNAPSHOT_FILE = SNAPSHOT_DIR / "company_brain_snapshot.json"


async def export_graph_snapshot(
    dataset_name: str = "company_brain",
    output_path: Path | str | None = None,
) -> Path:
    """Export the current FalkorDB graph to a JSON snapshot file."""
    out_file = Path(output_path) if output_path else DEFAULT_SNAPSHOT_FILE
    out_file.parent.mkdir(parents=True, exist_ok=True)

    print(f"Exporting graph snapshot for dataset '{dataset_name}' to {out_file}...")

    # 1. Fetch all nodes with their internal ID, primary label, and properties
    nodes_query = (
        "MATCH (n) "
        "RETURN id(n), labels(n), properties(n)"
    )
    nodes_res = await query_graph(nodes_query, dataset_name=dataset_name)

    nodes_data: list[dict[str, Any]] = []
    id_map: dict[int, int] = {}  # old_internal_id -> export_index
    for idx, row in enumerate(nodes_res):
        if not row:
            continue
        old_id, labels, props = row[0], row[1], row[2]
        id_map[old_id] = idx
        nodes_data.append(
            {
                "export_id": idx,
                "labels": labels,
                "properties": props or {},
            }
        )

    # 2. Fetch all edges with start node, end node, type, and properties
    edges_query = (
        "MATCH (a)-[r]->(b) "
        "RETURN id(a), type(r), properties(r), id(b)"
    )
    edges_res = await query_graph(edges_query, dataset_name=dataset_name)

    edges_data: list[dict[str, Any]] = []
    for row in edges_res:
        if not row:
            continue
        start_id, rel_type, props, end_id = row[0], row[1], row[2], row[3]
        if start_id in id_map and end_id in id_map:
            edges_data.append(
                {
                    "src_export_id": id_map[start_id],
                    "type": rel_type,
                    "properties": props or {},
                    "tgt_export_id": id_map[end_id],
                }
            )

    mem_usage = await get_falkordb_memory_usage()

    snapshot_payload = {
        "dataset_name": dataset_name,
        "exported_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "falkordb_memory": mem_usage,
        "nodes_count": len(nodes_data),
        "edges_count": len(edges_data),
        "nodes": nodes_data,
        "edges": edges_data,
    }

    out_file.write_text(json.dumps(snapshot_payload, indent=2), encoding="utf-8")
    print(
        f"Snapshot successfully saved: {len(nodes_data)} nodes, {len(edges_data)} edges -> {out_file}"
    )
    return out_file


async def restore_graph_snapshot(
    dataset_name: str = "company_brain",
    snapshot_path: Path | str | None = None,
) -> dict[str, Any]:
    """Restore FalkorDB graph from a JSON snapshot without any LLM calls."""
    snap_file = Path(snapshot_path) if snapshot_path else DEFAULT_SNAPSHOT_FILE
    if not snap_file.exists():
        raise FileNotFoundError(f"Snapshot file not found at: {snap_file}")

    print("\n" + "=" * 65)
    print(f"RESTORING GRAPH SNAPSHOT: '{snap_file.name}' INTO '{dataset_name}'")
    print("=" * 65)

    start_time = time.perf_counter()

    with open(snap_file, mode="r", encoding="utf-8") as f:
        data = json.load(f)

    # 1. Reset dataset and recreate graph
    print("[1/4] Resetting dataset graph...")
    await reset(dataset_name=dataset_name, delete_all_graphs=True)
    await get_or_create_dataset_graph_name(dataset_name)

    # 2. Re-create all nodes
    print(f"[2/4] Restoring {len(data['nodes'])} nodes...")
    export_to_new_id: dict[int, int] = {}

    for node in data["nodes"]:
        export_id = node["export_id"]
        labels = node["labels"]
        props = node["properties"]
        label_str = ":".join(labels) if labels else "Entity"

        # Create node with properties
        if props:
            create_q = f"CREATE (n:{label_str}) SET n += $props RETURN id(n)"
            res = await query_graph(create_q, dataset_name=dataset_name, params={"props": props})
        else:
            create_q = f"CREATE (n:{label_str}) RETURN id(n)"
            res = await query_graph(create_q, dataset_name=dataset_name)
        if res and res[0]:
            export_to_new_id[export_id] = res[0][0]

    # 3. Re-create all edges
    print(f"[3/4] Restoring {len(data['edges'])} edges...")
    for edge in data["edges"]:
        src_new = export_to_new_id.get(edge["src_export_id"])
        tgt_new = export_to_new_id.get(edge["tgt_export_id"])
        rel_type = edge["type"]
        props = edge.get("properties") or {}

        if src_new is not None and tgt_new is not None:
            if props:
                rel_q = (
                    f"MATCH (a) WHERE id(a) = $src_id "
                    f"MATCH (b) WHERE id(b) = $tgt_id "
                    f"CREATE (a)-[r:{rel_type}]->(b) SET r += $props"
                )
                await query_graph(
                    rel_q,
                    dataset_name=dataset_name,
                    params={"src_id": src_new, "tgt_id": tgt_new, "props": props},
                )
            else:
                rel_q = (
                    f"MATCH (a) WHERE id(a) = $src_id "
                    f"MATCH (b) WHERE id(b) = $tgt_id "
                    f"CREATE (a)-[r:{rel_type}]->(b)"
                )
                await query_graph(
                    rel_q,
                    dataset_name=dataset_name,
                    params={"src_id": src_new, "tgt_id": tgt_new},
                )

    elapsed = time.perf_counter() - start_time
    mem_final = await get_falkordb_memory_usage()

    # 4. Inventory counts
    node_count_res = await query_graph("MATCH (n) RETURN count(n)", dataset_name=dataset_name)
    edge_count_res = await query_graph("MATCH ()-[r]->() RETURN count(r)", dataset_name=dataset_name)
    actual_nodes = node_count_res[0][0] if node_count_res else 0
    actual_edges = edge_count_res[0][0] if edge_count_res else 0

    print("\n[4/4] Restoration Verification:")
    print(f"  - Nodes Restored: {actual_nodes} (expected: {data['nodes_count']})")
    print(f"  - Edges Restored: {actual_edges} (expected: {data['edges_count']})")
    print(f"  - Memory:         {mem_final.get('used_memory_human', 'N/A')} ({mem_final.get('used_memory')} bytes)")
    print(f"  - Elapsed Time:   {elapsed:.2f}s")
    print("=" * 65 + "\n")

    return {
        "status": "success",
        "nodes": actual_nodes,
        "edges": actual_edges,
        "elapsed_sec": round(elapsed, 2),
        "falkordb_memory": mem_final,
    }


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "restore"
    target = sys.argv[2] if len(sys.argv) > 2 else "company_brain"

    if action == "export":
        asyncio.run(export_graph_snapshot(dataset_name=target))
    else:
        asyncio.run(restore_graph_snapshot(dataset_name=target))
