"""Stable, human-readable decision codes (DEC-01, DEC-02, ...)."""

from typing import Optional

from app.brain.memory import query_graph

_UNDATED = "9999-12-31"


def assign_decision_codes(decisions: list[tuple[str, str, Optional[str]]]) -> dict[str, str]:
    """Map decision id -> code, numbering by decision date, then title, then id.

    The ordering depends only on each decision's own date and title, so a given set of decisions
    always gets the same codes. Undated decisions sort last.
    """
    ordered = sorted(
        decisions,
        key=lambda d: ((d[2] or "")[:10] or _UNDATED, d[1].lower(), d[0]),
    )
    width = max(2, len(str(len(ordered))))
    return {d[0]: f"DEC-{i:0{width}d}" for i, d in enumerate(ordered, start=1)}


async def get_decision_codes(dataset_name: Optional[str] = None) -> dict[str, str]:
    """Decision codes for every Decision in the graph."""
    rows = await query_graph(
        "MATCH (d:Decision) RETURN d.id, d.title, d.decided_on", dataset_name=dataset_name
    )
    return assign_decision_codes(
        [(str(r[0]), str(r[1] or ""), str(r[2]) if r[2] else None) for r in rows if r and r[0]]
    )
