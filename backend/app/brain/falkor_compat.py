"""FalkorDB Adapter Compatibility Layer for Cognee 1.6.

Architectural Decision: Provenance Preservation via Adapter Subclassing
------------------------------------------------------------------------
In Cognee 1.6.3, GraphDBInterface expanded its method signatures:
  - add_nodes(nodes, source_ref_key: str | None = None, pipeline_run_id: str | None = None)
  - add_edges(edges, source_ref_key: str | None = None, pipeline_run_id: str | None = None)

These parameters enable Cognee's document-level provenance tracking and dataset
rollback/pruning features. However, cognee-community-hybrid-adapter-falkor v0.3.1
implemented add_nodes(self, nodes) and add_edges(self, edges) without accepting
these keyword arguments, resulting in:
  TypeError: FalkorDBAdapter.add_nodes() got an unexpected keyword argument 'source_ref_key'

Decision:
  Rather than silently swallowing these arguments via (*args, **kwargs),
  PatchedFalkorDBAdapter actively attaches source_ref_key and pipeline_run_id to the
  persisted node and edge properties in FalkorDB.

  Benefits:
  1. Full signature compliance with Cognee 1.6's GraphDBInterface.
  2. Preserves graph provenance directly in FalkorDB: OpenCypher queries can filter
     nodes and relationships by source document and ingestion pipeline run.
  3. Uses Cognee's supported extension point `use_graph_adapter("falkor", ...)`.
  4. Requires zero edits to third-party vendor code.
"""

from typing import Any, Union

from cognee.infrastructure.databases.graph import use_graph_adapter
from cognee.infrastructure.databases.graph.graph_db_interface import EdgeData, Node
from cognee.infrastructure.engine import DataPoint
from cognee_community_hybrid_adapter_falkor import register  # noqa: F401
from cognee_community_hybrid_adapter_falkor.falkor_adapter import FalkorDBAdapter


class PatchedFalkorDBAdapter(FalkorDBAdapter):
    """Subclass of FalkorDBAdapter providing Cognee 1.6 provenance parameter compatibility."""

    async def add_nodes(
        self,
        nodes: Union[list[Node], list[DataPoint]],
        source_ref_key: str | None = None,
        pipeline_run_id: str | None = None,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        """Add multiple nodes to the graph, enriching properties with provenance metadata.

        Args:
            nodes: List of Node tuples (node_id, properties) or DataPoint instances.
            source_ref_key: Optional document/chunk source reference identifier.
            pipeline_run_id: Optional ingestion pipeline run identifier.
        """
        if not nodes:
            return

        augmented_nodes: list[Any] = []
        for node in nodes:
            if isinstance(node, tuple) and len(node) == 2:
                node_id, properties = node
                props = dict(properties) if properties else {}
                if source_ref_key is not None and "source_ref_key" not in props:
                    props["source_ref_key"] = source_ref_key
                if pipeline_run_id is not None and "pipeline_run_id" not in props:
                    props["pipeline_run_id"] = pipeline_run_id
                augmented_nodes.append((node_id, props))
            elif isinstance(node, DataPoint):
                # DataPoint instance: attach provenance metadata if set
                if source_ref_key is not None and hasattr(node, "__dict__"):
                    node_props = dict(node.__dict__)
                    node_props["source_ref_key"] = source_ref_key
                    if pipeline_run_id is not None:
                        node_props["pipeline_run_id"] = pipeline_run_id
                    augmented_nodes.append((str(node.id), node_props))
                else:
                    augmented_nodes.append(node)
            else:
                augmented_nodes.append(node)

        await super().add_nodes(augmented_nodes)

    async def add_edges(
        self,
        edges: list[EdgeData],
        source_ref_key: str | None = None,
        pipeline_run_id: str | None = None,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        """Add multiple edges to the graph, enriching edge properties with provenance metadata.

        Args:
            edges: List of EdgeData tuples (source_id, target_id, relationship_name, properties).
            source_ref_key: Optional document/chunk source reference identifier.
            pipeline_run_id: Optional ingestion pipeline run identifier.
        """
        if not edges:
            return

        augmented_edges: list[EdgeData] = []
        for edge in edges:
            if isinstance(edge, tuple) and len(edge) == 4:
                source_id, target_id, rel_name, properties = edge
                props = dict(properties) if properties else {}
                if source_ref_key is not None and "source_ref_key" not in props:
                    props["source_ref_key"] = source_ref_key
                if pipeline_run_id is not None and "pipeline_run_id" not in props:
                    props["pipeline_run_id"] = pipeline_run_id
                augmented_edges.append((source_id, target_id, rel_name, props))
            else:
                augmented_edges.append(edge)

        await super().add_edges(augmented_edges)


# Register the patched adapter as the official "falkor" graph provider in Cognee
use_graph_adapter("falkor", PatchedFalkorDBAdapter)
