"""Backfill verbatim source text and per-source quotes into an existing graph, in place.

- Ticket.body  <- tickets.csv `comments` (first 1,500 chars)
- Meeting.body <- the meeting note file (first 1,500 chars)
- BASED_ON.quote <- the decision's evidence quote where the source text contains it, else the
  source's own verbatim sentence stating the decision (if one exists)

Never deletes anything and never re-runs extraction, so it is safe on the production graph.
Idempotent. Usage: PYTHONPATH=backend python scripts/backfill_source_text.py [dataset] [--dry-run]
"""

import asyncio
import csv
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.brain.memory import query_graph
from app.ingest.notes_source import parse_meeting_note
from app.ingest.source_text import meeting_body, quote_in, sentence_stating, ticket_body


async def backfill(dataset: str, dry_run: bool = False) -> dict[str, int]:
    counts = {"tickets": 0, "meetings": 0, "edge_quotes": 0, "quotes_not_found": 0}

    rows = list(csv.DictReader(io.StringIO((ROOT / "data" / "tickets.csv").read_text(encoding="utf-8"))))
    for row in rows:
        if not dry_run:
            res = await query_graph(
                "MATCH (t:Ticket {ticket_id: $tid}) SET t.body = $body RETURN count(t)",
                dataset_name=dataset,
                params={"tid": row["ticket_id"].strip(), "body": ticket_body(row)},
            )
            counts["tickets"] += res[0][0] if res else 0
        else:
            counts["tickets"] += 1

    for path in sorted((ROOT / "data" / "meeting_notes").glob("*.md")):
        content = path.read_text(encoding="utf-8")
        title = parse_meeting_note(content, path.name)["title"]
        if not dry_run:
            res = await query_graph(
                "MATCH (m:Meeting {title: $title}) SET m.body = $body RETURN count(m)",
                dataset_name=dataset,
                params={"title": title, "body": meeting_body(content)},
            )
            counts["meetings"] += res[0][0] if res else 0
        else:
            counts["meetings"] += 1

    # Per-source quotes: only where the decision's quote is found in that source's text
    edges = await query_graph(
        "MATCH (d:Decision)-[r:based_on]->(src) "
        "RETURN d.id, d.evidence_quote, id(src), src.body, r.quote, d.title",
        dataset_name=dataset,
    )
    for d_id, quote, src_id, body, existing, title in edges:
        if existing:
            continue
        if not quote_in(quote, body):
            quote = sentence_stating(title, body)
        if quote:
            counts["edge_quotes"] += 1
            if not dry_run:
                await query_graph(
                    "MATCH (d:Decision {id: $d})-[r:based_on]->(src) WHERE id(src) = $src "
                    "SET r.quote = $quote",
                    dataset_name=dataset,
                    params={"d": d_id, "src": src_id, "quote": quote},
                )
        else:
            counts["quotes_not_found"] += 1
    return counts


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    result = asyncio.run(backfill(args[0] if args else "company_brain", "--dry-run" in sys.argv))
    print(result)
