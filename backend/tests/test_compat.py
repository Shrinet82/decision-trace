"""Unit tests for the FalkorDB compatibility adapter layer."""

import inspect
from unittest.mock import AsyncMock, patch

import pytest
from cognee_community_hybrid_adapter_falkor.falkor_adapter import FalkorDBAdapter

from app.brain.falkor_compat import PatchedFalkorDBAdapter


def test_patched_adapter_signature():
    """Verify that PatchedFalkorDBAdapter accepts source_ref_key and pipeline_run_id."""
    sig_nodes = inspect.signature(PatchedFalkorDBAdapter.add_nodes)
    assert "source_ref_key" in sig_nodes.parameters
    assert "pipeline_run_id" in sig_nodes.parameters

    sig_edges = inspect.signature(PatchedFalkorDBAdapter.add_edges)
    assert "source_ref_key" in sig_edges.parameters
    assert "pipeline_run_id" in sig_edges.parameters


@pytest.mark.asyncio
async def test_add_nodes_attaches_provenance():
    """Test that add_nodes enriches node dictionaries with provenance metadata."""
    adapter = PatchedFalkorDBAdapter.__new__(PatchedFalkorDBAdapter)

    test_nodes = [
        ("node_1", {"name": "Alice"}),
        ("node_2", {"name": "Bob"}),
    ]

    with patch.object(FalkorDBAdapter, "add_nodes", new_callable=AsyncMock) as mock_super_add:
        await adapter.add_nodes(
            test_nodes,
            source_ref_key="doc_101",
            pipeline_run_id="run_abc",
        )

        mock_super_add.assert_called_once()
        passed_nodes = mock_super_add.call_args[0][0]
        assert len(passed_nodes) == 2
        assert passed_nodes[0][1]["source_ref_key"] == "doc_101"
        assert passed_nodes[0][1]["pipeline_run_id"] == "run_abc"
        assert passed_nodes[1][1]["source_ref_key"] == "doc_101"


@pytest.mark.asyncio
async def test_add_edges_attaches_provenance():
    """Test that add_edges enriches edge dictionaries with provenance metadata."""
    adapter = PatchedFalkorDBAdapter.__new__(PatchedFalkorDBAdapter)

    test_edges = [
        ("node_1", "node_2", "OWNS", {"created_at": "2026-10-11"}),
    ]

    with patch.object(FalkorDBAdapter, "add_edges", new_callable=AsyncMock) as mock_super_add:
        await adapter.add_edges(
            test_edges,
            source_ref_key="doc_101",
            pipeline_run_id="run_abc",
        )

        mock_super_add.assert_called_once()
        passed_edges = mock_super_add.call_args[0][0]
        assert len(passed_edges) == 1
        assert passed_edges[0][3]["source_ref_key"] == "doc_101"
        assert passed_edges[0][3]["pipeline_run_id"] == "run_abc"
