# utils/candidates.py
from __future__ import annotations
from typing import Any, Dict, List, Optional
from copy import deepcopy
import json

from ..config import logger, get_gemini_llm, LLM_MODEL_LITE_NAME, MAX_RETRIES
from ..prompts.judge import JUDGE_PROMPT


def run_candidate(graph, base_state: Dict[str, Any]) -> Dict[str, Any]:
    """Run the full graph once on a deepcopy of base_state and return players/events."""
    state = deepcopy(base_state)
    final_state = graph.invoke(state)
    analysis = final_state.get("final_analysis") or {}
    players = analysis.get("players") or []
    events = analysis.get("events") or []
    return {
        "players": players,
        "events": events,
        "meta": {
            "validation_issues": final_state.get("validation_issues"),
            "attempts": final_state.get("attempts"),
            "teams": final_state.get("teams"),
        },
        "state": final_state,
    }


def judge_select(candidates: List[Dict[str, Any]], commentary: str, teams: Dict[str, Any]) -> Dict[str, Any]:
    """Ask the LLM Judge to pick the best candidate based on structured scores."""
    llm = get_gemini_llm(model_name=LLM_MODEL_LITE_NAME, temperature=0.1)
    from pydantic import BaseModel, Field

    class JudgePerCandidate(BaseModel):
        evidence_coverage: float
        roster_consistency: float
        chronology_ok: int
        db_alignment: float
        rule_violations: int
        composite_score: float

    class JudgeDecision(BaseModel):
        per_candidate: List[JudgePerCandidate]
        winner_index: int

    structured = llm.with_structured_output(JudgeDecision).with_retry(
        retry_if_exception_type=(Exception,), stop_after_attempt=MAX_RETRIES, wait_exponential_jitter=True
    )
    chain = JUDGE_PROMPT | structured

    # Compact candidates to JSON-safe dicts (players/events Pydantic models are fine when dumped via jsonable from API, but here keep simple)
    safe_candidates = []
    for c in candidates:
        safe_candidates.append({
            "players": [p.model_dump() if hasattr(p, 'model_dump') else p for p in c.get("players", [])],
            "events": [e.model_dump() if hasattr(e, 'model_dump') else e for e in c.get("events", [])],
        })

    try:
        if not isinstance(teams, dict):
            teams = {}
        result: JudgeDecision = chain.invoke({
            "commentary": commentary,
            "home_team": teams.get("home_team", ""),
            "away_team": teams.get("away_team", ""),
            "candidates_json": json.dumps(safe_candidates, ensure_ascii=False)
        })
        return result.model_dump()
    except Exception as e:
        logger.warning(f"Judge failed or returned invalid JSON: {e}")
        # Fallback: pick the candidate with the most events, then most players
        best_idx = 0
        best_tuple = (-1, -1)
        for i, c in enumerate(candidates):
            t = (len(c.get("events", [])), len(c.get("players", [])))
            if t > best_tuple:
                best_tuple = t
                best_idx = i
        return {"per_candidate": [], "winner_index": best_idx}


def analyze_with_candidates(graph, base_state: Dict[str, Any], k: int = 3) -> Dict[str, Any]:
    """Run K candidates using same prompts/settings; judge to select the best."""
    logger.info(f"Candidates: running {k} times")
    candidates = [run_candidate(graph, base_state) for _ in range(max(1, k))]
    # Build compact evidence pack (use what processing saved if available)
    evidence_pack = base_state.get("review_evidence") or []
    # Judge sees only candidates and compact evidence
    decision = judge_select(candidates, "\n\n".join(evidence_pack) if evidence_pack else "", base_state.get("teams", {}))
    winner_idx = int(decision.get("winner_index", 0))
    winner = candidates[winner_idx]
    return {
        "state": winner.get("state", {}),
        "candidates": candidates,
        "decision": decision,
        "winner_index": winner_idx,
    }
