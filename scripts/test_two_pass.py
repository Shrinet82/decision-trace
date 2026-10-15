"""Test script to validate Two-Pass Extraction logic on positive and negative documents."""

import asyncio
import json
from typing import Literal, Optional
from pydantic import BaseModel, Field
from cognee.infrastructure.llm.LLMGateway import LLMGateway
from app.brain.memory import apply_groq_key, get_entity_roster


class CandidateDecision(BaseModel):
    title: str = Field(..., description="Concise title of the decision")
    verbatim_quote: str = Field(..., description="Exact verbatim text excerpt from the document that proves the choice was made")
    system: Optional[str] = Field(None, description="System/database/tool/service involved, or null")
    decided_by: Optional[str] = Field(None, description="Person who made or authorized the decision, or null")
    status: Literal["accepted", "proposed", "rejected", "reverted"] = Field(default="accepted")
    confidence: float = Field(default=0.8, description="0.0 to 1.0 confidence")
    rationale: str = Field(default="", description="Why the choice was made, constraints, or trade-offs")
    supersedes: list[str] = Field(default_factory=list, description="Titles of prior decisions superseded")
    contradicts: list[str] = Field(default_factory=list, description="Titles of decisions contradicted")


class Pass1Candidates(BaseModel):
    candidates: list[CandidateDecision] = Field(default_factory=list)


class Pass2Verification(BaseModel):
    was_choice_made: bool = Field(..., description="Was a definitive choice about technology, vendor, process, or policy made in the quote?")
    is_decision_not_status_or_bug: bool = Field(..., description="Is this an actual decision rather than a bug fix, pod restart, temporary incident triage, or routine status update?")
    decided_by_verified: Optional[str] = Field(None, description="Verified full name of the decider resolved from the text/roster, or null")
    system_verified: Optional[str] = Field(None, description="Verified canonical system name, or null")
    refined_title: str = Field(..., description="Clean, precise canonical decision title")
    keep: bool = Field(..., description="True if this is a valid decision supported by the quote; False if weak, routine bug, or non-decision")
    rejection_reason: Optional[str] = Field(None, description="Reason for rejection if keep is False")


PASS1_SYSTEM_PROMPT = """You are a high-recall information extraction engine for an engineering Company Brain.
Extract all candidate engineering decisions from the provided text.

DEFINITION:
A Decision is a choice about technology, vendor, process, or policy that is adopted, rejected, deprecated, migrated, upgraded to a specific version, or standardized, even when written as routine work, maintenance, or troubleshooting.

GENERIC DECISION EXAMPLES (for reference, NOT from the dataset):
- "Adopt SQLite in WAL mode for local desktop cache to prevent filesystem locks during multi-process read operations."
- "Standardize on TLS 1.3 across all edge load balancers and deprecate CBC-mode ciphers to meet PCI-DSS compliance."

EXPLICIT NON-DECISIONS (Do NOT extract):
- Bug reports (e.g. stack traces, null pointer exceptions, CSS styling defects).
- Incident debugging and root cause triage without a permanent technology or policy choice (e.g. restarting a crashed pod, bumping memory limit to survive a leak, checking connection queue metrics).
- Routine status updates or progress sharing (e.g. sprint burndown updates, standup notes, vacation schedules, completion percentages).
- Questions, inquiries, or open discussion without a chosen path.

RULES:
1. Provide an exact 'verbatim_quote' from the text that directly proves the choice.
2. If no choice was made, return candidates: [].
"""

PASS2_SYSTEM_PROMPT = """You are a strict precision verification engine for engineering decisions.
Evaluate the candidate decision against its verbatim evidence quote.

VERIFICATION CRITERIA:
1. was_choice_made: Did the team or individual actually make a definitive choice about technology, vendor, process, or policy in the quote?
2. is_decision_not_status_or_bug: Is this an actual decision, or is it a routine bug fix, temporary operational workaround (e.g. pod restart, memory bump), or progress status?
3. decider: Does the quote identify who made or approved the decision? Map to full name if identifiable from context.
4. system: What real system, vendor, or tool is affected? Strip any 'System:' prefix.
5. keep: Set to True ONLY if was_choice_made is True, is_decision_not_status_or_bug is True, and the choice is directly supported by the quote. If weak, speculative, or a routine bug/status, set keep=False.
"""

TEST_DOCS = [
    {
        "id": "TICK-103 (Positive: Maintenance framing)",
        "text": """Source Type: Ticket
Ticket ID: TICK-103
Title: Slow analytical queries on historical clickstream datasets
Reporter: Nina Simone
Assignee: Fiona Gallagher
System: Snowflake
Comment: After evaluating data warehouse capacity for ad-hoc aggregations, Fiona Gallagher decided: Adopt Snowflake for analytics ETL queries to decouple reporting compute from transactional systems. System: Snowflake.""",
        "expected_keep": True,
    },
    {
        "id": "TICK-H204 (Negative: Bug triage / Pod restart)",
        "text": """Source Type: Ticket
Ticket ID: TICK-H204
Title: Memory leak alert on notification worker pod replica 4
Reporter: Julia Roberts
Assignee: Evan Wright
System: Kubernetes
Comment: Pod was crashing with OOMKilled code 137 under peak load. Profiling traced the issue to an unclosed XML parser buffer in the email template renderer. Bumped the pod memory limit from 512Mi to 1Gi and restarted the deployment. Memory has stabilized.""",
        "expected_keep": False,
    },
    {
        "id": "2026-11-25_weekly_standup.md (Negative: Routine Standup)",
        "text": """Source Type: Meeting
Meeting Title: Weekly Engineering Sync and Sprint Standup
Date: 2026-11-25
Attended by: Alice Vance, Carlos Mendez, Dave Miller, Fiona Gallagher, Kevin Flynn
Note Content: Routine team check-in and sprint progress tracking.
- Alice Vance reported frontend refactoring is 80% complete and on track for sprint demo on Thursday.
- Carlos Mendez discussed ongoing ticket backlog grooming and planned PTO for the Thanksgiving holiday.
- Dave Miller shared that staging cluster CPU metrics are stable.
- Fiona Gallagher reminded the team about the upcoming compliance training deadline next Tuesday.
No new architectural, process, or vendor decisions were made.""",
        "expected_keep": False,
    },
]


async def run_two_pass(doc: dict):
    print(f"\n==================================================")
    print(f"Testing: {doc['id']}")
    print(f"--- PASS 1 (Recall) ---")
    p1_res = await LLMGateway.acreate_structured_output(
        doc["text"], PASS1_SYSTEM_PROMPT, Pass1Candidates
    )
    candidates = p1_res.candidates if hasattr(p1_res, "candidates") else []
    print(f"Pass 1 extracted {len(candidates)} candidate(s):")
    for c in candidates:
        print(f"  - Title: {c.title}")
        print(f"    Quote: {c.verbatim_quote}")
        print(f"    Decider: {c.decided_by} | System: {c.system}")

    verified = []
    if not candidates:
        print("Pass 1 produced 0 candidates -> Correct for negatives!")
    else:
        print(f"--- PASS 2 (Precision Verification) ---")
        for c in candidates:
            p2_input = (
                f"Candidate Title: {c.title}\n"
                f"Candidate Decider: {c.decided_by}\n"
                f"Candidate System: {c.system}\n"
                f"Candidate Status: {c.status}\n"
                f"Candidate Rationale: {c.rationale}\n"
                f"Evidence Quote: {c.verbatim_quote}\n"
                f"Source Document:\n{doc['text']}"
            )
            p2_res = await LLMGateway.acreate_structured_output(
                p2_input, PASS2_SYSTEM_PROMPT, Pass2Verification
            )
            print(f"  Candidate: '{c.title}'")
            print(f"    keep: {p2_res.keep} (was_choice_made={p2_res.was_choice_made}, is_decision={p2_res.is_decision_not_status_or_bug})")
            print(f"    refined_title: {p2_res.refined_title}")
            print(f"    decided_by: {p2_res.decided_by_verified}")
            print(f"    system: {p2_res.system_verified}")
            if not p2_res.keep:
                print(f"    rejection_reason: {p2_res.rejection_reason}")
            else:
                verified.append(p2_res)

    print(f"Final Verified Count: {len(verified)} (Expected keep={doc['expected_keep']})")


async def main():
    apply_groq_key()
    for doc in TEST_DOCS:
        await run_two_pass(doc)
        await asyncio.sleep(1.0)


if __name__ == "__main__":
    asyncio.run(main())
