"""Memory and Knowledge Graph Orchestration Layer.

This is the SINGLE module in the application that interfaces directly with Cognee.
It wraps ingestion, extraction (cognify), retrieval (search/ask), graph querying,
and dataset reset operations with typed async signatures, timeouts, and retries.
"""

import asyncio
import logging
from typing import Any, Optional

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.brain.models import CompanyBrainGraph
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


async def resolve_active_graph_name(dataset_name: Optional[str] = None) -> str:
    """Resolve the active FalkorDB graph name for a given dataset."""
    engine = await get_graph_engine()
    default_name = getattr(engine, "graph_name", _settings.DATASET_NAME)
    if not dataset_name:
        return default_name

    existing_graphs = await list_falkordb_graphs()
    if dataset_name in existing_graphs:
        return dataset_name

    try:
        from cognee.modules.data.methods import get_datasets_by_name
        from cognee.modules.users.methods import get_default_user

        user = await get_default_user()
        if user:
            ds_list = await get_datasets_by_name(dataset_name, user.id)
            if ds_list:
                uuid_str = str(ds_list[0].id)
                if uuid_str in existing_graphs:
                    return uuid_str
    except Exception:
        pass

    return default_name


async def get_existing_decision_titles(dataset_name: Optional[str] = None) -> list[str]:
    """Retrieve titles of all existing Decision nodes from the knowledge graph.

    Args:
        dataset_name: Target dataset name.

    Returns:
        list[str]: Unique decision titles currently in the graph.
    """
    try:
        engine = await get_graph_engine()
        driver = getattr(engine, "driver", None)
        graph_name = await resolve_active_graph_name(dataset_name)
        if driver and graph_name:
            res = driver.execute_command(
                "GRAPH.QUERY", graph_name, "MATCH (d:Decision) RETURN DISTINCT d.title"
            )
            titles = [
                row[0].decode() if isinstance(row[0], bytes) else str(row[0])
                for row in (res[1] if len(res) > 1 else [])
                if row and row[0] and str(row[0]).strip()
            ]
            return sorted(titles)

        results = await engine.query("MATCH (d:Decision) RETURN DISTINCT d.title as title")
        titles = [row[0] for row in results if row and row[0] and str(row[0]).strip()]
        return sorted(titles)
    except Exception as exc:
        logger.warning("Failed to fetch existing decision titles: %s", exc)
        return []


def build_extraction_prompt(existing_decision_titles: Optional[list[str]] = None) -> str:
    """Build the system prompt for Company Brain knowledge graph extraction."""
    base_prompt = (
        "You are an expert system analyst extracting a structured knowledge graph for an engineering Company Brain.\n"
        "Extract nodes and relationships strictly according to the provided schema.\n\n"
        "EXTRACTION RULES:\n"
        "1. Real Systems Only:\n"
        "   - In the 'systems' list and 'about_system' field, extract ONLY real databases, tools, services, or vendors (e.g. 'Postgres', 'Redis', 'ClickHouse', 'Keycloak', 'Kafka').\n"
        "   - Never include headers, prefixes, or labels such as 'System: Keycloak', 'System', or generic terms. Strip any 'System:' prefix.\n\n"
        "2. Tickets & Meetings:\n"
        "   - Only create a Ticket node if an explicit ticket identifier exists in the text (e.g. 'TICKET-842'). If no ticket is mentioned, leave 'tickets' empty and 'based_on' as null.\n"
        "   - Only create a Meeting node if an explicit meeting is described in the text (e.g. 'Q3 Architecture Sync'). If no meeting is mentioned, leave 'meetings' empty and 'based_on_meeting' as null.\n\n"
        "3. Null vs Empty Strings for Reference Fields:\n"
        "   - For relationship reference fields ('decided_by', 'about_system', 'about_project', 'based_on', 'based_on_meeting', 'based_on_document', 'supersedes', 'contradicts'):\n"
        "     If there is no corresponding entity, you MUST output null (or an empty list for list fields).\n"
        '     NEVER output empty strings ("") or placeholder text.\n\n'
        "4. Entity Identity Consistency:\n"
        "   - Reference fields must use the EXACT same identifier defined in the top-level entity lists (e.g. 'name' for Person/System, 'ticket_id' for Ticket, 'title' for Meeting and Decision).\n"
    )

    if existing_decision_titles:
        titles_str = "\n".join(f'  - "{t}"' for t in existing_decision_titles)
        base_prompt += (
            f"\n5. Existing Decisions (Identity Reuse):\n"
            f"The following decisions already exist in the knowledge base:\n"
            f"{titles_str}\n"
            f"When a decision in the text supersedes, contradicts, or updates an existing decision, "
            f"you MUST reuse the EXACT title string from the list above in the 'supersedes' or 'contradicts' array.\n"
        )
    return base_prompt


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((TimeoutError, asyncio.TimeoutError)),
    reraise=True,
)
async def ingest_text(
    text: str,
    dataset_name: Optional[str] = None,
    run_cognify: bool = True,
    graph_model: Optional[Any] = None,
    custom_prompt: Optional[str] = None,
    reconcile: bool = True,
) -> dict[str, Any]:
    """Ingest raw text into the unified knowledge graph.

    Args:
        text: The document or text excerpt to ingest.
        dataset_name: Target dataset name (defaults to configured unified dataset).
        run_cognify: Whether to immediately run entity extraction and graph construction.
        graph_model: Optional Pydantic DataPoint model (defaults to CompanyBrainGraph).
        custom_prompt: Optional custom extraction system prompt.
        reconcile: Whether to run post-ingest decision identity reconciliation.

    Returns:
        dict containing ingestion status and dataset metadata.
    """
    target_dataset = dataset_name or _settings.DATASET_NAME
    logger.info("Ingesting text into dataset '%s' (length: %d chars)", target_dataset, len(text))

    try:
        await cognee.add(text, dataset_name=target_dataset)
        if run_cognify:
            target_model = graph_model or CompanyBrainGraph

            # 2a: Supply existing decision titles to cognify prompt
            if custom_prompt is None:
                existing_titles = await get_existing_decision_titles(target_dataset)
                extraction_prompt = build_extraction_prompt(existing_titles)
            else:
                extraction_prompt = custom_prompt

            logger.info(
                "Running cognify on dataset '%s' with model '%s'...",
                target_dataset,
                getattr(target_model, "__name__", str(target_model)),
            )
            await cognee.cognify(
                datasets=[target_dataset],
                graph_model=target_model,
                custom_prompt=extraction_prompt,
            )
            logger.info("Cognify completed successfully for '%s'.", target_dataset)

            if reconcile:
                # 2b: Run post-ingest reconciliation step
                from app.brain.reconciliation import reconcile_decisions

                reconcile_res = await reconcile_decisions(target_dataset)
                logger.info("Reconciliation result for '%s': %s", target_dataset, reconcile_res)

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


async def query_graph(
    query: str,
    dataset_name: Optional[str] = None,
    params: Optional[dict[str, Any]] = None,
) -> list[Any]:
    """Execute a Cypher query on the dataset's FalkorDB graph.

    Args:
        query: Cypher query string.
        dataset_name: Optional target dataset name.
        params: Optional query parameters.

    Returns:
        list[Any]: Query result rows.
    """
    engine = await get_graph_engine()
    target_graph = await resolve_active_graph_name(dataset_name)
    driver = getattr(engine, "driver", None)
    if driver and target_graph:
        graph = driver.select_graph(target_graph)
        res = graph.query(query, params or {})
        return res.result_set if res.result_set else []
    return await engine.query(query, params or {})


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
    nodes_query = f"MATCH (n) RETURN id(n) as internal_id, n.id as entity_id, labels(n) as labels, properties(n) as props LIMIT {limit}"
    edges_query = (
        f"MATCH (s)-[r]->(t) "
        f"RETURN id(s) as source_id, id(t) as target_id, type(r) as relationship, properties(r) as props "
        f"LIMIT {limit}"
    )

    try:
        nodes_res = await query_graph(nodes_query, dataset_name=dataset_name)
        edges_res = await query_graph(edges_query, dataset_name=dataset_name)

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


async def list_falkordb_graphs() -> list[str]:
    """List all graph names currently existing in the FalkorDB instance.

    Returns:
        list[str]: Names of graphs stored in FalkorDB.
    """
    try:
        engine = await get_graph_engine()
        driver = getattr(engine, "driver", None)
        if driver:
            graphs_raw = driver.execute_command("GRAPH.LIST")
            return [g.decode() if isinstance(g, bytes) else str(g) for g in (graphs_raw or [])]
        return []
    except Exception as exc:
        logger.warning("Failed to list FalkorDB graphs: %s", exc)
        return []


async def reset(dataset_name: Optional[str] = None, delete_all_graphs: bool = False) -> list[str]:
    """Reset the knowledge base, clearing graph nodes in FalkorDB and local vector indexes.

    Args:
        dataset_name: Specific dataset to prune (defaults to configured DATASET_NAME).
        delete_all_graphs: If True, delete ALL graphs on the FalkorDB instance.
            Default is False (only deletes the specified or configured dataset graph).

    Returns:
        list[str]: Remaining graphs in FalkorDB after deletion.
    """
    target_dataset = dataset_name or _settings.DATASET_NAME
    logger.warning(
        "Resetting Company Brain knowledge base (dataset: %s, delete_all_graphs: %s)...",
        target_dataset,
        delete_all_graphs,
    )
    try:
        # Pre-resolve the target dataset's active graph name BEFORE pruning local metadata
        graphs_to_delete: set[str] = set()
        if not delete_all_graphs:
            if target_dataset:
                graphs_to_delete.add(target_dataset)
            if dataset_name:
                graphs_to_delete.add(dataset_name)
            try:
                active_g = await resolve_active_graph_name(target_dataset)
                if active_g:
                    graphs_to_delete.add(active_g)
            except Exception:
                pass

        # 1. Prune local data and system metadata
        await prune.prune_data()
        await prune.prune_system(metadata=True)

        # 2. Delete the graph(s) directly on the FalkorDB instance
        remaining_graphs: list[str] = []
        try:
            engine = await get_graph_engine()
            driver = getattr(engine, "driver", None)
            if driver:
                graphs_raw = driver.execute_command("GRAPH.LIST")
                existing_graphs = [
                    g.decode() if isinstance(g, bytes) else str(g) for g in (graphs_raw or [])
                ]
                for g_name in existing_graphs:
                    if delete_all_graphs:
                        driver.execute_command("GRAPH.DELETE", g_name)
                        logger.info("Deleted FalkorDB graph (delete_all_graphs): %s", g_name)
                    elif g_name in graphs_to_delete:
                        driver.execute_command("GRAPH.DELETE", g_name)
                        logger.info("Deleted FalkorDB dataset graph: %s", g_name)

                updated_graphs_raw = driver.execute_command("GRAPH.LIST")
                remaining_graphs = [
                    g.decode() if isinstance(g, bytes) else str(g)
                    for g in (updated_graphs_raw or [])
                ]
        except Exception as falkor_err:
            logger.warning("FalkorDB graph deletion error: %s", falkor_err)

        logger.info(
            "Knowledge base reset completed. Remaining FalkorDB graphs: %s", remaining_graphs
        )
        return remaining_graphs
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
