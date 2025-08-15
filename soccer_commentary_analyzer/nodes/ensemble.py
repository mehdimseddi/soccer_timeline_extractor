# nodes/ensemble.py
from __future__ import annotations
from copy import deepcopy
from typing import Any, Dict, List, Optional

from ..state_type.types_utils import CommentaryState
from ..config import logger
from .player_extraction import player_extraction_node
from .normalization import normalize_players_node
from .player_deduplication import deduplicate_players_node
from .composition import enforce_valid_team_composition
from .processing import process_segments_node
from .sync_events_with_final_players import sync_events_with_final_players_node
from .event_deduplication import deduplicate_events_node
from .validation import validate_analysis_node
from .reviewer import reviewer_node


class Knobs:
    def __init__(self, player_variant: Optional[str] = None, events_variant: Optional[str] = None):
        self.player_variant = player_variant
        self.events_variant = events_variant


def _compute_db_alignment(players: List[Any], events: List[Any], teams: Dict[str, str]) -> float:
    if not events:
        return 0.0
    player_names = {p.name for p in players if getattr(p, 'name', None)}
    allowed_teams = {teams.get('home_team'), teams.get('away_team')}
    ok = 0
    for ev in events:
        if (getattr(ev, 'player', None) in player_names) and (getattr(ev, 'team', None) in allowed_teams):
            ok += 1
    return ok / max(1, len(events))


def _composite_score(scores: Dict[str, Any], db_align: float) -> float:
    ev_cov = float(scores.get('evidence_coverage') or 0.0)
    roster = float(scores.get('roster_consistency') or 0.0)
    chrono = 1.0 if (scores.get('chronology_ok') == 1) else 0.0
    viol = float(scores.get('rule_violations') or 0.0)
    # Normalize violations assuming 0..5 typical
    viol_norm = min(1.0, viol / 5.0)
    return 0.35*ev_cov + 0.30*roster + 0.20*chrono + 0.15*db_align - 0.10*viol_norm


def _run_pipeline_once(base_state: CommentaryState, knobs: Knobs) -> Dict[str, Any]:
    s = deepcopy(base_state)
    # Optional: in future, use knobs to tweak prompts; for now, pass through
    s = player_extraction_node(s)
    s = normalize_players_node(s)
    s = deduplicate_players_node(s)
    s = enforce_valid_team_composition(s)
    s = process_segments_node(s)
    s = sync_events_with_final_players_node(s)
    s = deduplicate_events_node(s)
    s = validate_analysis_node(s)
    s = reviewer_node(s)  # applies edits and may store scores/decision
    # Pull reviewer scores if present
    rev_scores = s.get('reviewer_scores') or {}  # optional future storage point
    # As a fallback, try to infer from last reviewer output attached to state
    # but current reviewer stores decision only; prompt enforces scores to exist
    return {
        'players': s.get('extracted_players', []),
        'events': s.get('extracted_events', []),
        'scores': rev_scores,
        'state': s,
    }


def ensemble_generate_and_select_node(state: CommentaryState) -> CommentaryState:
    logger.info("Ensemble: generating candidates")
    base = _run_pipeline_once(state, Knobs())
    candidates = [base]
    # Simple diversity: rerun twice more (you can add real knobs later)
    for i in range(2):
        cand = _run_pipeline_once(state, Knobs())
        candidates.append(cand)

    # Score each candidate
    selection_scores: List[Dict[str, Any]] = []
    best_idx = 0
    best_score = -1.0
    for idx, cand in enumerate(candidates):
        players = cand['players']
        events = cand['events']
        teams = state.get('teams') or {}
        db_align = _compute_db_alignment(players, events, teams)
        scores = cand.get('scores') or {}
        composite = _composite_score(scores, db_align)
        selection_scores.append({'db_alignment': db_align, 'reviewer_scores': scores, 'composite': composite})
        logger.info(f"Ensemble: candidate {idx} composite={composite:.3f} db_align={db_align:.3f} scores={scores}")
        if composite > best_score:
            best_score = composite
            best_idx = idx

    chosen = candidates[best_idx]
    logger.info(f"Ensemble: selected candidate {best_idx} with composite={best_score:.3f}")

    # If score is low, ask for a retry path via reviewer decision signal (players vs events)
    decision = 'finalize'
    try:
        scores = chosen.get('scores') or {}
        if (float(scores.get('evidence_coverage') or 0.0) < 0.7) or (float(scores.get('roster_consistency') or 0.0) < 0.8):
            # Determine weakest axis by crude heuristic
            decision = 'retry_players' if len(chosen['players']) < 8 else 'retry_events'
    except Exception:
        pass

    # Write back into main state
    state['extracted_players'] = chosen['players']
    state['extracted_events'] = chosen['events']
    state['candidates'] = [{'players': c['players'], 'events': c['events']} for c in candidates]
    state['selected_candidate_index'] = best_idx
    state['selection_scores'] = selection_scores
    state['review_decision'] = decision
    return state
