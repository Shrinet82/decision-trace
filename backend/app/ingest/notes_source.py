"""Deterministic Meeting Notes Source Ingestion (No LLM).

Reads meeting_notes/*.md and creates Meeting nodes (title, date) and
attended_by edges from the note headers without an LLM, matching against
canonical Person nodes in FalkorDB.
"""

import logging
from pathlib import Path
from typing import Any, Optional

from app.brain.memory import get_or_create_dataset_graph_name, query_graph
from app.brain.models import Meeting
from app.config import get_settings

logger = logging.getLogger("decision_trace.ingest.notes")
_settings = get_settings()

DEFAULT_NOTES_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "meeting_notes"


def parse_meeting_note(content: str, filename: str) -> dict[str, Any]:
    """Extract meeting header metadata (title, date, attendees, notes) from markdown."""
    title = ""
    date = ""
    attendees: list[str] = []
    notes_lines: list[str] = []

    is_notes = False
    for line in content.splitlines():
        trimmed = line.strip()
        if trimmed.startswith("Meeting:"):
            title = trimmed.split("Meeting:", 1)[1].strip()
        elif trimmed.startswith("Date:"):
            date = trimmed.split("Date:", 1)[1].strip()
        elif trimmed.startswith("Attended by:"):
            raw_attendees = trimmed.split("Attended by:", 1)[1].strip()
            attendees = [a.strip() for a in raw_attendees.split(",") if a.strip()]
        elif trimmed.startswith("Notes:"):
            is_notes = True
            notes_lines.append(trimmed.split("Notes:", 1)[1].strip())
        elif is_notes:
            notes_lines.append(trimmed)

    # Fallback to filename if title is missing
    if not title:
        title = Path(filename).stem.replace("_", " ").title()

    return {
        "title": title,
        "date": date,
        "attendees": attendees,
        "notes": "\n".join(notes_lines).strip(),
        "filename": filename,
    }


async def ingest_notes_source(
    notes_dir: Optional[str | Path] = None,
    dataset_name: Optional[str] = None,
) -> dict[str, Any]:
    """Ingest deterministic Meeting nodes and attended_by edges from markdown files into FalkorDB.

    Args:
        notes_dir: Directory containing markdown meeting notes.
        dataset_name: Target dataset name.

    Returns:
        dict: Counts of meetings and edges created.
    """
    dir_path = Path(notes_dir or DEFAULT_NOTES_DIR)
    if not dir_path.exists():
        raise FileNotFoundError(f"Meeting notes directory not found at: {dir_path}")

    target_dataset = dataset_name or _settings.DATASET_NAME
    graph_name = await get_or_create_dataset_graph_name(target_dataset)
    logger.info(
        "Ingesting meeting notes from %s into dataset '%s' (graph: %s)...",
        dir_path,
        target_dataset,
        graph_name,
    )

    counts = {
        "meetings": 0,
        "attended_by_edges": 0,
    }

    note_files = sorted(dir_path.glob("*.md"))
    for file_path in note_files:
        content = file_path.read_text(encoding="utf-8")
        parsed = parse_meeting_note(content, file_path.name)

        title = parsed["title"]
        m_dp = Meeting(title=title)
        m_node_id = str(m_dp.id)
        m_title_esc = title.replace("'", "\\'")
        m_date_esc = parsed["date"].replace("'", "\\'")
        m_file_esc = parsed["filename"].replace("'", "\\'")

        # Merge Meeting node
        await query_graph(
            f"MERGE (m:Meeting {{id: '{m_node_id}'}}) "
            f"ON CREATE SET m.title = '{m_title_esc}', m.date = '{m_date_esc}', "
            f"m.meeting_date = '{m_date_esc}', m.file_name = '{m_file_esc}' "
            f"ON MATCH SET m.title = '{m_title_esc}', m.date = '{m_date_esc}', "
            f"m.meeting_date = '{m_date_esc}', m.file_name = '{m_file_esc}'",
            dataset_name=target_dataset,
        )
        counts["meetings"] += 1

        # Link attended_by edges
        for attendee in parsed["attendees"]:
            att_esc = attendee.replace("'", "\\'")
            res = await query_graph(
                f"MATCH (m:Meeting {{id: '{m_node_id}'}}), (p:Person {{name: '{att_esc}'}}) "
                f"MERGE (m)-[r:attended_by]->(p) RETURN count(r)",
                dataset_name=target_dataset,
            )
            if res and res[0][0] > 0:
                counts["attended_by_edges"] += 1

    logger.info("Meeting notes deterministic ingestion completed: %s", counts)
    return counts
