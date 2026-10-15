"""Diagnose the 7 misses from Step 6 evaluation.

Prints the source text, model raw output, and classifications for:
D03, D10, D11, D12, D13, D14, D16
"""

import asyncio
import json
from pathlib import Path
import pandas as pd
from cognee.infrastructure.llm.LLMGateway import LLMGateway
from cognee.shared.llm_graph_model import datapoint_model_to_basemodel
from app.brain.models import CompanyBrainGraph
from app.brain.memory import build_extraction_prompt
from app.ingest.notes_source import parse_meeting_note

MISSED_ITEMS = [
    {
        "id": "D03",
        "source_id": "TICK-103",
        "type": "ticket",
        "expected_title": "Adopt Snowflake for analytics ETL queries",
        "decider": "Fiona Gallagher",
    },
    {
        "id": "D10",
        "source_id": "TICK-110",
        "type": "ticket",
        "expected_title": "Deprecate legacy RabbitMQ clusters in favor of native Redis PubSub for low-volume notifications",
        "decider": "Ian Malcolm",
    },
    {
        "id": "D11",
        "source_id": "TICK-111",
        "type": "ticket",
        "expected_title": "Use Keycloak OAuth2 tokens for internal API gateway authentication",
        "decider": "Julia Roberts",
    },
    {
        "id": "D12",
        "source_id": "TICK-112",
        "type": "ticket",
        "expected_title": "Upgrade all production Postgres instances to version 16",
        "decider": "Evan Wright",
    },
    {
        "id": "D13",
        "source_id": "2026-02-10_iam_modernization.md",
        "type": "meeting",
        "expected_title": "Adopt Keycloak for company-wide single sign-on",
        "decider": "Julia Roberts",
    },
    {
        "id": "D14",
        "source_id": "2026-04-12_observability_sync.md",
        "type": "meeting",
        "expected_title": "Migrate application metrics from Datadog to Prometheus Operator",
        "decider": "Kevin Flynn",
    },
    {
        "id": "D16",
        "source_id": "2026-08-20_container_platform_upgrade.md",
        "type": "meeting",
        "expected_title": "Standardize on Kubernetes 1.30 across all production regions",
        "decider": "Laura Croft",
    },
]


def get_item_text(item: dict) -> str:
    if item["type"] == "ticket":
        df = pd.read_csv("data/tickets.csv")
        row = df[df["ticket_id"] == item["source_id"]].iloc[0]
        return (
            f"Source Type: Ticket\n"
            f"Ticket ID: {row['ticket_id']}\n"
            f"Title: {row.get('title', '')}\n"
            f"Reporter: {row.get('reporter', '')}\n"
            f"Assignee: {row.get('assignee', '')}\n"
            f"System: {row.get('system', '')}\n"
            f"Comment: {row['comments']}"
        )
    else:
        path = Path("data/meeting_notes") / item["source_id"]
        parsed = parse_meeting_note(path.read_text(encoding="utf-8"), path.name)
        return (
            f"Source Type: Meeting\n"
            f"Meeting Title: {parsed['title']}\n"
            f"Date: {parsed['date']}\n"
            f"Attended by: {', '.join(parsed['attendees'])}\n"
            f"Note Content: {parsed.get('notes', '')}"
        )


async def main():
    prompt = build_extraction_prompt()
    simplified_model = datapoint_model_to_basemodel(CompanyBrainGraph, strip_metadata=True)

    counts = {"a": 0, "b": 0, "c": 0, "d": 0}

    print("=" * 80)
    print("STEP 7 DIAGNOSIS: 7 MISSES FROM STEP 6 EVALUATION")
    print("=" * 80)

    for item in MISSED_ITEMS:
        text = get_item_text(item)
        print(f"\n" + "-" * 70)
        print(f"Item: [{item['id']}] | Source: {item['source_id']} ({item['type']})")
        print(f"Expected Decision: '{item['expected_title']}' by {item['decider']}")
        print(f"\n--- [1] SOURCE TEXT ---")
        print(text)

        error_msg = None
        raw_res = None
        try:
            raw_res = await LLMGateway.acreate_structured_output(text, prompt, simplified_model)
        except Exception as exc:
            error_msg = str(exc)

        print(f"\n--- [2] MODEL RAW STRUCTURED OUTPUT ---")
        if error_msg:
            print(f"Error: {error_msg}")
            classification = "(c) schema/parse failure"
            reason = f"LLM execution threw: {error_msg}"
            counts["c"] += 1
        else:
            dump = raw_res.model_dump() if hasattr(raw_res, "model_dump") else raw_res
            print(json.dumps(dump, indent=2, default=str))

            decisions = dump.get("decisions", []) if isinstance(dump, dict) else []
            if len(decisions) == 0:
                # The prompt rule:
                # "Do NOT extract routine bug investigations, parameter tweaks, troubleshooting notes, or operational checks where no architectural or technology decision was made. If the text only describes standard debugging or investigation without an architectural/technology decision, leave 'decisions' empty ([])."
                classification = "(a) prompt told it to skip"
                reason = "Blanket suppression rule in Prompt Rule 5: Ticket/note framed as routine troubleshooting/investigation ('Slow analytical queries', 'Memory pressure', 'Replication lag', etc.) triggered the prompt's instruction to output empty decisions []."
                counts["a"] += 1
            else:
                classification = "(d) removed by dedup/reconciliation"
                reason = f"Model produced {len(decisions)} decision(s), but in full run it was dropped/overwritten during dedup/reconciliation or failed evaluation similarity threshold."
                counts["d"] += 1

        print(f"\n--- [3] CLASSIFICATION ---")
        print(f"Classification: {classification}")
        print(f"Reason: {reason}")
        print("-" * 70)
        await asyncio.sleep(1.0)  # Rate limit safety

    print("\n" + "=" * 80)
    print("SUMMARY COUNTS ACROSS THE 7 MISSES:")
    print(f"  (a) Prompt told it to skip:           {counts['a']}")
    print(f"  (b) Model judged not a decision:      {counts['b']}")
    print(f"  (c) Schema/parse failure:             {counts['c']}")
    print(f"  (d) Removed by dedup/reconciliation:  {counts['d']}")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
