"""Choosing the decision an /ask answer is mainly about."""

from typing import Optional


def _lead(title: str, words: int = 5) -> str:
    return " ".join(title.lower().split()[:words])


def pick_primary_decision(
    answer: str,
    decisions: list[tuple[str, str]],
    first_citation_index: dict[str, int],
    superseded: set[str],
) -> Optional[str]:
    """Return the id of the decision the answer is mainly about, or None if there are none.

    Each candidate (id, title) is scored:
      +2   its title (first five words, since models quote shortened titles) appears in the answer
      +1   it is based on a cited source; earlier citations win ties (-0.01 per position)
      -1.5 it has already been superseded by a newer decision
    The first highest-scoring candidate wins, so the result is deterministic.
    """
    answer_l = answer.lower()
    best_id: Optional[str] = None
    best_score = float("-inf")
    for d_id, title in decisions:
        score = 0.0
        lead = _lead(title)
        if len(lead.split()) >= 3 and lead in answer_l:
            score += 2
        if d_id in first_citation_index:
            score += 1 - 0.01 * first_citation_index[d_id]
        if d_id in superseded:
            score -= 1.5
        if score > best_score:
            best_id, best_score = d_id, score
    return best_id
