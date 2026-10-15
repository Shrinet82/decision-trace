"""Memory and Knowledge Graph Orchestration Layer.

This is the SINGLE module in the application that interfaces directly with Cognee.
It wraps ingestion, extraction (cognify), retrieval (search/ask), graph querying,
and dataset reset operations with typed async signatures, timeouts, and retries.
"""

import asyncio
import logging
import os
from typing import Any, Optional

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import export_cognee_env, get_settings

# 1. Initialize settings and export required environment variables
_settings = get_settings()

from app.brain.models import CompanyBrainGraph

# 2. Register FalkorDB compatibility adapter BEFORE importing cognee
# 3. Import cognee and its engine modules
import cognee  # noqa: E402
from cognee import SearchType, prune  # noqa: E402
from cognee.infrastructure.databases.graph import get_graph_engine  # noqa: E402

# Re-export environment in case Cognee's internal dotenv loader clobbered preset env vars
export_cognee_env(_settings)

import app.brain.falkor_compat  # noqa: F401, E402

logger = logging.getLogger("decision_trace.memory")

_GROQ_API_KEYS: list[str] = [
    k
    for k in [
        os.getenv("SECONDARY_GROQ_API_KEY", ""),
        _settings.LLM_API_KEY.get_secret_value() if _settings.LLM_API_KEY else "",
    ]
    if k
]
if not _GROQ_API_KEYS:
    _GROQ_API_KEYS = [""]
_current_key_idx: int = 0


def get_active_groq_key() -> str:
    global _current_key_idx
    return _GROQ_API_KEYS[_current_key_idx % len(_GROQ_API_KEYS)]


def rotate_groq_key() -> str:
    global _current_key_idx
    _current_key_idx += 1
    new_key = get_active_groq_key()
    logger.info("Rotated Groq API key to pool index %d", _current_key_idx % len(_GROQ_API_KEYS))
    apply_groq_key(new_key)
    return new_key


def apply_groq_key(key: Optional[str] = None) -> None:
    active_model = os.getenv("LLM_MODEL", _settings.LLM_MODEL)
    if active_model.startswith("bedrock/"):
        target_key = key or (
            _settings.BEDROCK_API_KEY.get_secret_value()
            if getattr(_settings, "BEDROCK_API_KEY", None)
            else _settings.LLM_API_KEY.get_secret_value()
        )
        os.environ["AWS_BEARER_TOKEN_BEDROCK"] = target_key
        os.environ["LLM_API_KEY"] = target_key
        os.environ["LLM_MODEL"] = active_model
        os.environ.pop("LLM_ENDPOINT", None)
        os.environ.pop("GROQ_API_KEY", None)
        os.environ.pop("OPENAI_API_KEY", None)
        os.environ["AWS_REGION_NAME"] = getattr(_settings, "AWS_REGION_NAME", "us-east-1")
        os.environ["AWS_DEFAULT_REGION"] = getattr(_settings, "AWS_REGION_NAME", "us-east-1")
        try:
            from cognee.infrastructure.llm.config import get_llm_config

            get_llm_config.cache_clear()
            cfg = get_llm_config()
            cfg.llm_api_key = target_key
            cfg.llm_model = active_model
            cfg.llm_endpoint = None
            cfg.llm_temperature = 0.0
            if cfg.llm_args is None:
                cfg.llm_args = {}
            cfg.llm_args["aws_region_name"] = getattr(_settings, "AWS_REGION_NAME", "us-east-1")
        except Exception:
            pass
        return

    target_key = key or get_active_groq_key()
    os.environ["LLM_API_KEY"] = target_key
    os.environ["GROQ_API_KEY"] = target_key
    os.environ["OPENAI_API_KEY"] = target_key
    try:
        from cognee.infrastructure.llm.config import get_llm_config

        get_llm_config.cache_clear()
        cfg = get_llm_config()
        cfg.llm_api_key = target_key
        cfg.llm_model = _settings.LLM_MODEL
    except Exception:
        pass


# Ensure active key is applied at import time
apply_groq_key()


class MemoryOperationError(Exception):
    """Raised when a memory ingestion or search operation fails."""

    pass


async def resolve_active_graph_name(dataset_name: Optional[str] = None) -> str:
    """Resolve the active FalkorDB graph name for a given dataset."""
    # Priority 1: If FALKORDB_GRAPH_NAME is configured, honor it directly for default datasets
    configured_graph = getattr(_settings, "FALKORDB_GRAPH_NAME", None)
    if configured_graph and (
        not dataset_name
        or dataset_name == "company_brain"
        or dataset_name == getattr(_settings, "DATASET_NAME", None)
    ):
        return configured_graph

    engine = await get_graph_engine()
    default_name = getattr(engine, "graph_name", _settings.DATASET_NAME)
    if not dataset_name:
        return configured_graph or default_name

    try:
        from cognee.infrastructure.databases.relational import create_db_and_tables
        from cognee.modules.data.methods import get_datasets_by_name
        from cognee.modules.users.methods import get_default_user

        await create_db_and_tables()
        user = await get_default_user()
        if user:
            ds_list = await get_datasets_by_name(dataset_name, user.id)
            if ds_list:
                uuid_str = str(ds_list[0].id)
                return uuid_str
    except Exception:
        pass

    existing_graphs = await list_falkordb_graphs()
    if dataset_name in existing_graphs:
        return dataset_name

    return dataset_name if dataset_name else (configured_graph or default_name)


async def get_or_create_dataset_graph_name(dataset_name: Optional[str] = None) -> str:
    """Resolve or register the active FalkorDB graph name for a given dataset."""
    target = dataset_name or _settings.DATASET_NAME

    try:
        from cognee.infrastructure.databases.relational import create_db_and_tables
        from cognee.modules.data.methods import get_datasets_by_name
        from cognee.modules.data.methods.create_authorized_dataset import create_authorized_dataset
        from cognee.modules.users.methods import get_default_user

        await create_db_and_tables()
        user = await get_default_user()
        if user:
            ds_list = await get_datasets_by_name(target, user.id)
            if ds_list:
                return str(ds_list[0].id)
            new_ds = await create_authorized_dataset(target, user)
            return str(new_ds.id)
    except Exception as exc:
        logger.warning("Failed to create or fetch dataset in cognee: %s", exc)

    return target


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


async def get_relevant_decision_titles(
    text: str,
    dataset_name: Optional[str] = None,
    top_n: int = 25,
) -> list[str]:
    """Retrieve top-N most similar existing decision titles using embedding similarity.

    Args:
        text: Target text being ingested.
        dataset_name: Target dataset name.
        top_n: Maximum number of relevant titles to return (default 25).

    Returns:
        list[str]: Ranked relevant decision titles.
    """
    all_titles = await get_existing_decision_titles(dataset_name)
    if not all_titles or len(all_titles) <= top_n:
        return all_titles

    try:
        from app.brain.reconciliation import compute_embedding_similarity

        scored = [(t, compute_embedding_similarity(text, t)) for t in all_titles]
        scored.sort(key=lambda x: x[1], reverse=True)
        return [t[0] for t in scored[:top_n]]
    except Exception as exc:
        logger.warning("Failed to rank decision titles by similarity: %s", exc)
        return all_titles[:top_n]


async def get_entity_roster(
    dataset_name: Optional[str] = None,
    max_people: int = 30,
    max_systems: int = 30,
) -> dict[str, list[str]]:
    """Retrieve known people and system names to serve as an extraction resolution roster.

    Args:
        dataset_name: Target dataset name.
        max_people: Maximum number of people names to include.
        max_systems: Maximum number of system names to include.

    Returns:
        dict: {'people': list[str], 'systems': list[str]}
    """
    people: list[str] = []
    systems: list[str] = []
    try:
        people_res = await query_graph(
            "MATCH (p:Person) RETURN DISTINCT p.name ORDER BY p.name",
            dataset_name=dataset_name,
        )
        people = [r[0] for r in people_res if r and r[0]][:max_people]

        sys_res = await query_graph(
            "MATCH (s:System) RETURN DISTINCT s.name ORDER BY s.name",
            dataset_name=dataset_name,
        )
        systems = [r[0] for r in sys_res if r and r[0]][:max_systems]
    except Exception as exc:
        logger.debug("Failed to fetch entity roster: %s", exc)
    return {"people": people, "systems": systems}


def build_extraction_prompt(
    existing_decision_titles: Optional[list[str]] = None,
    roster: Optional[dict[str, list[str]]] = None,
) -> str:
    """Build the system prompt for Company Brain knowledge graph extraction."""
    base_prompt = (
        "You are an expert system analyst extracting a structured knowledge graph for an engineering Company Brain.\n"
        "Extract nodes and relationships strictly according to the provided schema.\n\n"
        "EXTRACTION RULES:\n"
        "1. Real Systems Only:\n"
        "   - In the 'systems' list and 'about_system' field, extract ONLY real databases, tools, services, or vendors (e.g. 'Postgres', 'Redis', 'ClickHouse', 'Keycloak', 'Kafka').\n"
        "   - Never include headers, prefixes, or labels such as 'System: Keycloak', 'System', or generic terms. Strip any 'System:' prefix.\n\n"
        "2. Ticket and Meeting Linking (based_on):\n"
        "   - If extracting from a Ticket (e.g. 'Ticket ID: TICK-101'), set 'based_on' on the Decision to that exact Ticket ID (e.g. 'TICK-101'). Leave the top-level 'tickets' list empty.\n"
        "   - If extracting from a Meeting (e.g. 'Meeting: IAM Architecture Modernization'), set 'based_on_meeting' on the Decision to that exact Meeting Title. Leave the top-level 'meetings' list empty.\n"
        "   - If no ticket or meeting is referenced, leave 'based_on' and 'based_on_meeting' as null.\n\n"
        "3. Null vs Empty Strings for Reference Fields:\n"
        "   - For relationship reference fields ('decided_by', 'about_system', 'about_project', 'based_on', 'based_on_meeting', 'based_on_document', 'supersedes', 'contradicts'):\n"
        "     If there is no corresponding entity, you MUST output null (or an empty list for list fields).\n"
        '     NEVER output empty strings ("") or placeholder text.\n\n'
        "4. Entity Identity Consistency:\n"
        "   - Reference fields must use the EXACT same identifier defined in the top-level entity lists (e.g. 'name' for Person/System, 'ticket_id' for Ticket, 'title' for Meeting and Decision).\n\n"
        "5. Deliberate Decisions (General Definition):\n"
        "   - A Decision is a choice about technology, vendor, process, or policy that is adopted, rejected, deprecated, migrated, upgraded to a specific version, or standardized, even when written as routine work, maintenance, or troubleshooting.\n"
        "   - Generic Examples (NOT from dataset):\n"
        "     * 'Adopt SQLite in WAL mode for local desktop cache to prevent filesystem locks during multi-process read operations.'\n"
        "     * 'Standardize on TLS 1.3 across all edge load balancers and deprecate CBC-mode ciphers to meet PCI-DSS compliance.'\n"
        "   - Explicit Non-Decisions (Do NOT extract as decisions):\n"
        "     * Bug reports (e.g. stack traces, null pointer exceptions, CSS styling defects).\n"
        "     * Incident debugging and root cause triage without a permanent technology or policy choice (e.g. restarting a crashed pod, bumping memory limits to survive a leak, inspecting connection queue telemetry).\n"
        "     * Routine status updates or progress sharing (e.g. sprint burndown updates, standup notes, vacation schedules, completion percentages).\n"
        "     * Questions, inquiries, or open discussion without a chosen path.\n"
        "   - Even when framed as routine maintenance, quarterly review, or troubleshooting, if a choice about technology, vendor, process, or policy was adopted, rejected, deprecated, migrated, upgraded to a specific version, or standardized, extract it as a Decision.\n"
    )

    if existing_decision_titles:
        titles_str = "\n".join(f'  - "{t}"' for t in existing_decision_titles)
        base_prompt += (
            f"\n6. Existing Decisions (Identity Reuse):\n"
            f"The following decisions already exist in the knowledge base:\n"
            f"{titles_str}\n"
            f"When a decision in the text supersedes, contradicts, or updates an existing decision, "
            f"you MUST reuse the EXACT title string from the list above in the 'supersedes' or 'contradicts' array.\n"
        )

    if roster and (roster.get("people") or roster.get("systems")):
        people_list = ", ".join(f'"{p}"' for p in roster.get("people", []))
        systems_list = ", ".join(f'"{s}"' for s in roster.get("systems", []))
        base_prompt += (
            f"\n7. Known Entity Roster (Resolution Guide):\n"
            f"The company has the following known people and systems in its catalog:\n"
            f"- People: [{people_list}]\n"
            f"- Systems: [{systems_list}]\n"
            f"When text refers to an individual (e.g. 'Dave') or a system (e.g. 'the Redis cluster'), "
            f"resolve it to the EXACT corresponding canonical name from this roster (e.g. 'Dave Miller', 'Redis').\n"
        )
    return base_prompt


def build_pass1_prompt(
    existing_decision_titles: Optional[list[str]] = None,
    roster: Optional[dict[str, list[str]]] = None,
) -> str:
    """Build the Pass 1 (recall-oriented) system prompt extracting candidate decisions with verbatim evidence quotes."""
    prompt = (
        "You are a high-recall information extraction engine for an engineering Company Brain.\n"
        "Extract all candidate engineering decisions from the provided text.\n\n"
        "DECISION DEFINITION:\n"
        "A Decision is a choice about technology, vendor, process, configuration, or policy that is adopted, rejected, deprecated, migrated, upgraded to a specific version, standardized, or changed (including infrastructure parameters, timeouts, retention policies, partitioning, or caching strategies), even when written as routine work, maintenance, or troubleshooting.\n\n"
        "GENERIC EXAMPLES (for reference, NOT from the dataset):\n"
        "- 'Adopt SQLite in WAL mode for local desktop cache to prevent filesystem locks during multi-process read operations.'\n"
        "- 'Standardize on TLS 1.3 across all edge load balancers and deprecate CBC-mode ciphers to meet PCI-DSS compliance.'\n\n"
        "EXPLICIT NON-DECISIONS (Do NOT extract, return candidates: []):\n"
        "- Routine incident triage, operational bug fixes, and patch maintenance: investigating an alert or operational ticket, applying a temporary configuration patch or bug workaround, restarting services, or routine maintenance repairs. These are operational triage actions, NOT engineering decisions.\n"
        "- Operational threshold tuning or alert cleanups (e.g. connection timeouts, rate limit adjustments, disk watermark threshold alerts).\n"
        "- High-level meeting goals or themes without selecting a concrete tool, version, or policy (e.g. 'Focus will be on database connection stability').\n"
        "- Pure bug reports without a permanent policy/technology choice (e.g. stack traces, null pointer exceptions, CSS styling defects).\n"
        "- Temporary incident firefighting (e.g. restarting a crashed pod, bumping memory limits to survive a leak temporarily).\n"
        "- Routine status updates or progress sharing (e.g. sprint burndown updates, standup notes, vacation schedules, completion percentages).\n"
        "- Questions, inquiries, or open discussion without a chosen path.\n\n"
        "RULES:\n"
        "1. For each candidate decision, provide an exact 'verbatim_quote' from the text that directly proves the choice.\n"
        "2. Extract the canonical system/tool name into 'system' (e.g. 'Postgres', 'Redis', 'Keycloak', 'Snowflake', 'Kubernetes'). Strip any 'System:' prefix.\n"
        "3. Extract the person who made the decision into 'decided_by'.\n"
        "4. If no decision was made, return candidates: [].\n"
    )

    if existing_decision_titles:
        titles_str = "\n".join(f'  - "{t}"' for t in existing_decision_titles[:25])
        prompt += (
            f"\nEXISTING DECISIONS (for supersedes/contradicts matching):\n"
            f"{titles_str}\n"
        )

    if roster and (roster.get("people") or roster.get("systems")):
        people_list = ", ".join(f'"{p}"' for p in roster.get("people", []))
        systems_list = ", ".join(f'"{s}"' for s in roster.get("systems", []))
        prompt += (
            f"\nKNOWN ROSTER:\n"
            f"- People: [{people_list}]\n"
            f"- Systems: [{systems_list}]\n"
        )
    return prompt


def build_pass2_prompt(roster: Optional[dict[str, list[str]]] = None) -> str:
    """Build the Pass 2 (precision verification) system prompt."""
    prompt = (
        "You are a strict precision verification engine for engineering decisions in a Company Brain.\n"
        "Evaluate the candidate decision against its verbatim evidence quote and document context.\n\n"
        "VERIFICATION CRITERIA:\n"
        "1. was_choice_made: Did the team or individual make a definitive choice, approval, agreement, or standardization about technology, vendor, process, configuration, or policy in the quote? (e.g. 'we have decided to adopt', 'approved upgrading', 'standardized on').\n"
        "2. is_decision_not_status_or_bug: Is this an actual decision or policy/version/architectural change rather than routine debugging, a pod restart, temporary incident triage, or routine task update? Version upgrades, technology adoptions, and architectural migrations performed during maintenance or routine tickets COUNT as decisions.\n"
        "CRITICAL PRECISION RULES (Must reject with keep=False):\n"
        "- Routine Incident Resolutions: Applying a temporary bug patch, parameter tweak, operational workaround, or routine repair to close an operational support ticket is maintenance, NOT an engineering decision. Set keep=False, is_decision_not_status_or_bug=False, was_choice_made=False, and rejection_reason='Routine incident triage/operational fix'.\n"
        "- Operational Alarm Tuning: Tuning alert thresholds, timeouts, or disk watermarks to clear a monitoring alarm is routine operations, NOT a decision. Set keep=False.\n"
        "- Generic Meeting Goals: Stating general intent (e.g. 'Focus will be on database connection stability') without a concrete technology, version, or policy choice is NOT a decision. Set keep=False.\n"
        "3. decided_by_verified: Check if the decider is explicitly identified in the quote or document context. Resolve to their canonical full name from the roster.\n"
        "4. system_verified: Check the system affected. Strip any 'System:' prefix and match against the canonical system name.\n"
        "5. refined_title: Refine the decision title into a concise, professional title (e.g. 'Adopt Snowflake for analytics ETL queries', 'Upgrade production Postgres instances to version 16').\n"
        "6. keep: Set to True ONLY if was_choice_made is True, is_decision_not_status_or_bug is True, and the choice is directly supported by the quote. If weak, speculative, or a routine bug/status/incident resolution, set keep=False.\n"
    )
    if roster and (roster.get("people") or roster.get("systems")):
        people_list = ", ".join(f'"{p}"' for p in roster.get("people", []))
        systems_list = ", ".join(f'"{s}"' for s in roster.get("systems", []))
        prompt += (
            f"\nKNOWN CANONICAL ROSTER:\n"
            f"- People: [{people_list}]\n"
            f"- Systems: [{systems_list}]\n"
        )
    return prompt


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

            # 2a: Supply relevant existing decision titles and roster to cognify prompt
            if custom_prompt is None:
                relevant_titles = await get_relevant_decision_titles(
                    text, dataset_name=target_dataset, top_n=25
                )
                roster = await get_entity_roster(target_dataset)
                extraction_prompt = build_extraction_prompt(
                    existing_decision_titles=relevant_titles,
                    roster=roster,
                )
            else:
                extraction_prompt = custom_prompt

            logger.info(
                "Running cognify on dataset '%s' with model '%s'...",
                target_dataset,
                getattr(target_model, "__name__", str(target_model)),
            )
            apply_groq_key()
            engine = await get_graph_engine()
            target_graph = await resolve_active_graph_name(target_dataset)
            adapter = getattr(engine, "_engine", lambda: engine)()
            orig_graph = getattr(adapter, "graph_name", _settings.DATASET_NAME)
            if hasattr(adapter, "graph_name") and target_graph:
                adapter.graph_name = target_graph

            try:
                await cognee.cognify(
                    datasets=[target_dataset],
                    graph_model=target_model,
                    custom_prompt=extraction_prompt,
                )
            finally:
                if hasattr(adapter, "graph_name") and orig_graph:
                    adapter.graph_name = orig_graph

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
        apply_groq_key()
        engine = await get_graph_engine()
        target_graph = await resolve_active_graph_name(target_dataset)
        adapter = getattr(engine, "_engine", lambda: engine)()
        orig_graph = getattr(adapter, "graph_name", _settings.DATASET_NAME)
        if hasattr(adapter, "graph_name") and target_graph:
            adapter.graph_name = target_graph

        try:
            search_results = await cognee.search(
                query_type=SearchType.GRAPH_COMPLETION,
                query_text=question,
                datasets=[target_dataset],
            )
        finally:
            if hasattr(adapter, "graph_name") and orig_graph:
                adapter.graph_name = orig_graph

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
        if delete_all_graphs or not dataset_name:
            await prune.prune_data()
            await prune.prune_system(metadata=True)
        elif dataset_name:
            try:
                from cognee.infrastructure.databases.relational import get_relational_engine
                from sqlalchemy import text as sa_text
                rel_engine = get_relational_engine()
                async with rel_engine.get_async_session() as session:
                    await session.execute(
                        sa_text(
                            "DELETE FROM pipeline_runs WHERE dataset_id IN (SELECT id FROM datasets WHERE name = :ds)"
                        ),
                        {"ds": dataset_name},
                    )
                    await session.execute(
                        sa_text(
                            "DELETE FROM data WHERE dataset_id IN (SELECT id FROM datasets WHERE name = :ds)"
                        ),
                        {"ds": dataset_name},
                    )
                    await session.execute(
                        sa_text(
                            "DELETE FROM dataset_database WHERE dataset_id IN (SELECT id FROM datasets WHERE name = :ds)"
                        ),
                        {"ds": dataset_name},
                    )
                    await session.execute(
                        sa_text("DELETE FROM datasets WHERE name = :ds"),
                        {"ds": dataset_name},
                    )
                    await session.commit()
            except Exception as exc:
                logger.debug("Failed to prune dataset '%s' from relational db: %s", dataset_name, exc)

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


async def get_falkordb_memory_usage() -> dict[str, Any]:
    """Retrieve memory telemetry from FalkorDB instance.

    Returns:
        dict: Memory metrics (used_memory, used_memory_human, used_memory_peak_human).
    """
    try:
        engine = await get_graph_engine()
        driver = getattr(engine, "driver", None)
        if driver:
            info = driver.execute_command("INFO", "memory")
            if isinstance(info, dict):
                return {
                    "used_memory": info.get("used_memory"),
                    "used_memory_human": info.get("used_memory_human"),
                    "used_memory_peak_human": info.get("used_memory_peak_human"),
                }
    except Exception as exc:
        logger.warning("Failed to retrieve FalkorDB memory info: %s", exc)
    return {}
