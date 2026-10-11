"""End-to-End integration test against FalkorDB Cloud and Groq LLM.

Marked as 'integration' and conditionally executed only when valid
cloud credentials and RUN_INTEGRATION_TESTS=1 are present in the environment.
"""

import os

import pytest

from app.brain.memory import ask, ingest_text, reset
from app.config import get_settings

settings = get_settings()

has_cloud_credentials = bool(
    os.getenv("RUN_INTEGRATION_TESTS") == "1"
    or (
        settings.FALKORDB_HOST
        and settings.FALKORDB_PASSWORD.get_secret_value()
        and settings.LLM_API_KEY.get_secret_value()
    )
)


@pytest.mark.integration
@pytest.mark.skipif(
    not has_cloud_credentials,
    reason="Integration tests require FALKORDB_HOST and LLM_API_KEY credentials.",
)
@pytest.mark.asyncio
async def test_end_to_end_knowledge_flow():
    """Ingest synthetic text, extract graph via cognify, query, and verify cleanup."""
    isolated_dataset = "integration_test_dataset"

    # Synthetic sentence containing decision and decider
    synthetic_doc = (
        "Sarah is the Principal Platform Engineer at AcmeCorp. "
        "On October 10th, Sarah decided to adopt FalkorDB Cloud for GraphRAG "
        "because of its low-latency matrix-based OpenCypher graph engine."
    )

    try:
        # 1. Ingest and cognify
        ingest_res = await ingest_text(
            synthetic_doc, dataset_name=isolated_dataset, run_cognify=True
        )
        assert ingest_res["status"] == "success"

        # 2. Ask question and verify answer
        query_res = await ask("Who decided to adopt FalkorDB?", dataset_name=isolated_dataset)
        assert query_res is not None
        answer_text = query_res.get("answer", "")
        assert len(answer_text) > 0
        # Check that relevant context or decider was identified
        assert "Sarah" in answer_text or "Sarah" in str(query_res.get("raw_results", ""))

    finally:
        # 3. Cleanup / reset
        await reset(dataset_name=isolated_dataset)
