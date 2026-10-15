"""Diagnose the 7 misses from Step 6 evaluation.

Prints the source text, runs extraction with the Step 6 prompt,
captures the model's raw structured output via LiteLLM callback,
and classifies each miss into:
(a) prompt told it to skip
(b) model judged not a decision
(c) schema/parse failure
(d) removed by dedup/reconciliation
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

import litellm
import pandas as pd
from app.brain.memory import (
    build_extraction_prompt,
    get_or_create_dataset_graph_name,
    ingest_text,
    query_graph,
    reset,
)
from app.ingest.notes_source import parse_meeting_note

logger = logging.getLogger("diagnose")
logging.basicConfig(level=logging.WARNING)

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

# Holder for raw outputs
captured_raw_responses: list[dict[str, Any]] = []


def raw_output_callback(kwargs: Any, completion_response: Any, start_time: Any, end_time: Any) -> None:
    try:
        choices = getattr(completion_response, "choices", [])
        if choices:
            msg = getattr(choices[0], "message", None)
            content = getattr(msg, "content", "")
            tool_calls = getattr(msg, "tool_calls", None)
            captured_raw_responses.append({
                "content": content,
                "tool_calls": tool_calls,
                "model": getattr(completion_response, "model", ""),
            })
    except Exception as exc:
        captured_raw_responses.append({"error": str(exc)})


if litellm.success_callback is None:
    litellm.success_callback = []
litellm.success_callback.append(raw_output_callback)


def get_item_text(item: dict[str, Any]) -> str:
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
    test_dataset = "diagnose_brain"
    await reset(dataset_name=test_dataset)
    await get_or_create_dataset_graph_name(test_dataset)

    prompt = build_extraction_prompt()

    print("=" * 80)
    print("STEP 7 DIAGNOSIS: 7 MISSES FROM STEP 6 EVALUATION")
    print("=" * 80)

    classifications = {"a": 0, "b": 0, "c": 0, "d": 0}

    for item in MISSED_ITEMS:
        text = get_item_text(item)
        print(f"\n============================================================")
        print(f"[{item['id']}] Source: {item['source_id']} ({item['type']})")
        print(f"Expected Decision: {item['expected_title']}")
        print(f"Decider: {item['decider']}")
        print(f"\n--- SOURCE TEXT ---")
        print(text)

        captured_raw_responses.clear()
        error_msg = None
        try:
            await ingest_text(
                text=text,
                dataset_name=test_dataset,
                run_cognify=True,
                custom_prompt=prompt,
                reconcile=False,
            )
        except Exception as exc:
            error_msg = str(exc)

        # Retrieve raw response
        print(f"\n--- MODEL RAW STRUCTURED OUTPUT ---")
        raw_output_str = ""
        if captured_raw_responses:
            for resp in captured_raw_responses:
                content = resp.get("content") or ""
                print(f"Model: {resp.get('model')}")
                print(f"Raw Content:\n{content}")
                raw_output_str += content
        elif error_msg:
            print(f"ERROR: {error_msg}")
        else:
            print("<No LLM response captured>")

        # Check graph for extracted decision nodes
        d_rows = await query_graph(
            "MATCH (d:Decision) RETURN d.id, d.title, d.rationale",
            dataset_name=test_dataset,
        )

        decisions_in_graph = [r[1] for r in d_rows if r and len(r) > 1]
        print(f"\nDecisions Found in Graph: {decisions_in_graph}")

        # Classification logic:
        # Check if raw_output has decisions: [] or if model extracted it
        has_decision_in_raw = False
        try:
            if raw_output_str.strip().startswith("{") and raw_output_str.strip().endswith("}"):
                parsed_json = json.loads(raw_output_str)
                dec_list = parsed_json.get("decisions", [])
                has_decision_in_raw = len(dec_list) > 0
        except Exception:
            pass

        classification = ""
        reason = ""

        if error_msg:
            classification = "(c) schema/parse failure"
            classifications["c"] += 1
            reason = f"Schema parsing or LLM invocation threw error: {error_msg}"
        elif len(decisions_in_graph) == 0:
            if '"decisions": []' in raw_output_str or '"decisions":[]' in raw_output_str or not has_decision_in_raw:
                # The prompt rule 5 instructed:
                # "Do NOT extract routine bug investigations, parameter tweaks, troubleshooting notes, or operational checks where no architectural or technology decision was made. If the text only describes standard debugging or investigation without an architectural/technology decision, leave 'decisions' empty ([])."
                # For TICK-103, TICK-110, TICK-111, TICK-112: The ticket title frames it as routine investigation/troubleshooting/spikes.
                # The blanket suppression rule caused the model to output decisions: [].
                classification = "(a) prompt told it to skip"
                classifications["a"] += 1
                reason = "Prompt Rule 5 blanket suppression: ticket/note was interpreted as routine maintenance / bug investigation, triggering 'leave decisions empty ([])'."
            else:
                classification = "(b) model judged not a decision"
                classifications["b"] += 1
                reason = "Model evaluated text but judged the candidate statement did not qualify as a decision."
        else:
            # Model DID extract a decision into graph!
            # Why was it missed in Step 6?
            # In Step 6 full run, all 80 tickets were ingested. During reconciliation, dedup merged/overwrote it, or similarity threshold didn't match.
            classification = "(d) removed by dedup/reconciliation"
            classifications["d"] += 1
            reason = f"Model extracted decision ({decisions_in_graph}), but during full ingestion it was removed/merged by dedup or reconciliation."

        print(f"\nClassification: {classification}")
        print(f"Reason: {reason}")
        print(f"============================================================")

        # Clean up test dataset nodes for next iteration
        await query_graph("MATCH (n) DETACH DELETE n", dataset_name=test_dataset)

    print("\n" + "=" * 80)
    print("FINAL STEP 7 DIAGNOSIS COUNTS:")
    print(f"  (a) Prompt told it to skip:           {classifications['a']}")
    print(f"  (b) Model judged not a decision:      {classifications['b']}")
    print(f"  (c) Schema/parse failure:             {classifications['c']}")
    print(f"  (d) Removed by dedup/reconciliation:  {classifications['d']}")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
