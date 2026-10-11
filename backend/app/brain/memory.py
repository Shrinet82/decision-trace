"""Memory and Knowledge Graph Orchestration Layer.

This is the SINGLE module in the application that interfaces directly with Cognee.
It wraps ingestion, extraction (cognify), retrieval (search/ask), graph querying,
and dataset reset operations with typed async signatures, timeouts, and retries.
"""

import asyncio
import logging
from typing import Any, Optional

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import get_settings

# 1. Initialize settings and export required environment variables
_settings = get_settings()

# 2. Register FalkorDB compatibility adapter BEFORE importing cognee
# 3. Import cognee and its engine modules
import cognee  # noqa: E402
from cognee import SearchType, prune  # noqa: E402
from cognee.infrastructure.databases.graph import get_graph_engine  # noqa: E402

import app.brain.falkor_compat  # noqa: F401, E402

logger = logging.getLogger("decision_trace.memory")


class MemoryOperationError(Exception):
    """Raised when a memory ingestion or search operation fails."""

    pass


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((TimeoutError, asyncio.TimeoutError)),
    reraise=True,
)
async def ingest_text(
    text: str, dataset_name: Optional[str] = None, run_cognify: bool = True
) -> dict[str, Any]:
    """Ingest raw text into the unified knowledge graph.

    Args:
        text: The document or text excerpt to ingest.
        dataset_name: Target dataset name (defaults to configured unified dataset).
        run_cognify: Whether to immediately run entity extraction and graph construction.

    Returns:
        dict containing ingestion status and dataset metadata.
    """
    target_dataset = dataset_name or _settings.DATASET_NAME
    logger.info("Ingesting text into dataset '%s' (length: %d chars)", target_dataset, len(text))

    try:
        await cognee.add(text, dataset_name=target_dataset)
        if run_cognify:
            logger.info("Running cognify on dataset '%s'...", target_dataset)
            await cognee.cognify(datasets=[target_dataset])
            logger.info("Cognify completed successfully for '%s'.", target_dataset)

        return {"status": "success", "dataset": target_dataset, "cognified": run_cognify}
    except Exception as exc:
        logger.error("Failed to ingest text into dataset '%s': %s", target_dataset, exc)
        raise MemoryOperationError(f"Ingestion failed: {exc}") from exc


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=6),
    reraise=True,
)
async def ask(question: str, dataset_name: Optional[str] = None) -> dict[str, Any]:
    """Query the Company Brain using graph-augmented context.

    Args:
        question: Natural language question.
        dataset_name: Target dataset name to search.

    Returns:
        dict containing answer, citations, and raw search results.
    """
    target_dataset = dataset_name or _settings.DATASET_NAME
    logger.info("Querying Company Brain: '%s' (dataset: %s)", question, target_dataset)

    try:
        search_results = await cognee.search(
            query_type=SearchType.GRAPH_COMPLETION,
            query_text=question,
            datasets=[target_dataset],
        )

        formatted_answers: list[str] = []
        citations: list[str] = []

        if isinstance(search_results, list):
            for res in search_results:
                if isinstance(res, str):
                    formatted_answers.append(res)
                elif isinstance(res, dict):
                    formatted_answers.append(str(res.get("text", res.get("answer", res))))
                else:
                    formatted_answers.append(str(res))
        else:
            formatted_answers.append(str(search_results))

        combined_answer = (
            "\n\n".join(formatted_answers) if formatted_answers else "No relevant context found."
        )
        return {
            "question": question,
            "answer": combined_answer,
            "citations": citations,
            "raw_results": search_results,
        }
    except Exception as exc:
        logger.error("Failed to query Company Brain: %s", exc)
        raise MemoryOperationError(f"Query failed: {exc}") from exc


async def get_graph(
    dataset_name: Optional[str] = None, limit: int = 150
) -> dict[str, list[dict[str, Any]]]:
    """Retrieve graph topology (nodes and edges) directly from FalkorDB.

    Args:
        dataset_name: Target dataset name.
        limit: Maximum number of nodes and edges to return.

    Returns:
        dict with 'nodes' and 'edges' lists formatted for visualization.
    """
    engine = await get_graph_engine()
    nodes_query = f"MATCH (n) RETURN id(n) as internal_id, n.id as entity_id, labels(n) as labels, properties(n) as props LIMIT {limit}"
    edges_query = (
        f"MATCH (s)-[r]->(t) "
        f"RETURN id(s) as source_id, id(t) as target_id, type(r) as relationship, properties(r) as props "
        f"LIMIT {limit}"
    )

    try:
        nodes_res = await engine.query(nodes_query)
        edges_res = await engine.query(edges_query)

        nodes: list[dict[str, Any]] = []
        for row in nodes_res:
            internal_id = row[0]
            entity_id = row[1] or str(internal_id)
            labels = row[2] if len(row) > 2 else ["Entity"]
            props = row[3] if len(row) > 3 else {}
            # Mask any internal embedding vectors from response
            cleaned_props = {k: v for k, v in props.items() if not k.endswith("_vector")}
            nodes.append(
                {
                    "id": entity_id,
                    "label": labels[0] if labels else "Entity",
                    "labels": labels,
                    "properties": cleaned_props,
                }
            )

        edges: list[dict[str, Any]] = []
        for row in edges_res:
            source_id = str(row[0])
            target_id = str(row[1])
            relationship = row[2] if len(row) > 2 else "RELATES_TO"
            props = row[3] if len(row) > 3 else {}
            edges.append(
                {
                    "source": source_id,
                    "target": target_id,
                    "relationship": relationship,
                    "properties": props,
                }
            )

        return {"nodes": nodes, "edges": edges}
    except Exception as exc:
        logger.error("Failed to retrieve graph data: %s", exc)
        return {"nodes": [], "edges": []}


async def reset(dataset_name: Optional[str] = None) -> None:
    """Reset the knowledge base, clearing graph nodes and local vector indexes.

    Args:
        dataset_name: Specific dataset to prune, or all datasets if None.
    """
    logger.warning("Resetting Company Brain knowledge base...")
    try:
        await prune.prune_data()
        await prune.prune_system(metadata=True)
        logger.info("Knowledge base reset completed.")
    except Exception as exc:
        logger.error("Error during prune reset: %s", exc)
        raise MemoryOperationError(f"Reset failed: {exc}") from exc


async def ping_falkordb() -> bool:
    """Check connectivity to FalkorDB Cloud.

    Returns:
        bool: True if FalkorDB responds to a ping query, False otherwise.
    """
    try:
        engine = await get_graph_engine()
        res = await engine.query("RETURN 1 as ping")
        return bool(res and len(res) > 0)
    except Exception as exc:
        logger.error("FalkorDB ping failed: %s", exc)
        return False
