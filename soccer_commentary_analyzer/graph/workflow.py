# graph/workflow.py
from langgraph.graph import StateGraph, END
from ..nodes.cleaning import clean_commentary_node
from ..nodes.team_identification import identify_teams_node
from ..nodes.processing import process_segments_node
from ..nodes.composition import enforce_valid_team_composition
from ..nodes.validation import validate_analysis_node
from ..nodes.compile import compile_analysis_node
from ..nodes.normalization import normalize_players_node
from ..nodes.player_extraction import player_extraction_node 
from ..nodes.event_deduplication import deduplicate_events_node
from ..nodes.sync_events_with_final_players import sync_events_with_final_players_node
from ..config import logger
from ..state_type.types_utils import CommentaryState
from ..nodes.reviewer import reviewer_node
from ..nodes.finalize_team_codes_node import finalize_team_codes_node

def should_identify_teams(state: CommentaryState) -> str:
    if state.get("teams") and state["teams"].get("home_team") and state["teams"].get("away_team"):
        try:
            logger.info("Routing: identify_teams=skip (home=%s, away=%s)", state["teams"].get("home_team"), state["teams"].get("away_team"))
        except Exception:
            pass
        return "skip"
    try:
        logger.info("Routing: identify_teams=identify (no preset teams)")
    except Exception:
        pass
    return "identify"


def should_retry_validation(state: CommentaryState) -> str:
    if state["validation_issues"] and state["attempts"] < 3:
        # Adapt prompts by injecting discovered issues back into context (simplified here)
        logger.debug(f"Retrying due to validation issues (attempt {state['attempts'] + 1}): {state['validation_issues']}")
        try:
            logger.info("Routing: after_validation=retry attempts=%d issues=%d", state.get("attempts", 0), len(state.get("validation_issues", [])))
        except Exception:
            pass
        return "retry"
    try:
        logger.info("Routing: after_validation=done attempts=%d issues=%d", state.get("attempts", 0), len(state.get("validation_issues", [])))
    except Exception:
        pass
    return "done"


def build_soccer_analysis_graph():
    workflow = StateGraph(CommentaryState)
    workflow.add_node("clean_commentary", clean_commentary_node)
    workflow.add_node("identify_teams", identify_teams_node)
    workflow.add_node("extract_players", player_extraction_node)
    workflow.add_node("process_segments", process_segments_node)
    workflow.add_node("enforce_valid_team_composition", enforce_valid_team_composition)
    workflow.add_node("validate_analysis", validate_analysis_node)
    workflow.add_node("review_analysis", reviewer_node)
    workflow.add_node("compile_analysis", compile_analysis_node)
    workflow.add_node("normalize_players", normalize_players_node)
    from ..nodes.player_deduplication import deduplicate_players_node
    workflow.add_node("deduplicate_players", deduplicate_players_node)
    workflow.add_node("deduplicate_events", deduplicate_events_node)
    workflow.add_node("sync_events_with_final_players", sync_events_with_final_players_node)
    workflow.add_node("finalize_team_codes", finalize_team_codes_node)

    workflow.set_entry_point("clean_commentary")
    workflow.add_conditional_edges("clean_commentary", should_identify_teams, {"identify": "identify_teams", "skip": "extract_players"})
    workflow.add_edge("identify_teams", "extract_players")
    workflow.add_edge("extract_players", "normalize_players")
    workflow.add_edge("normalize_players", "deduplicate_players")
    workflow.add_edge("deduplicate_players", "enforce_valid_team_composition")
    workflow.add_edge("enforce_valid_team_composition", "process_segments")
    workflow.add_edge("process_segments", "sync_events_with_final_players")
    # workflow.add_edge("sync_events_with_final_players", "deduplicate_events")
    workflow.add_edge("sync_events_with_final_players", "finalize_team_codes")
    workflow.add_edge("finalize_team_codes", "deduplicate_events")
    workflow.add_edge("deduplicate_events", "validate_analysis")
    workflow.add_conditional_edges("validate_analysis", should_retry_validation, {"retry": "process_segments", "done": "final_deduplicate_events"})

    # Route based on reviewer decision
    def should_after_review(state: CommentaryState) -> str:
        decision = (state.get("review_decision") or "finalize").lower()
        attempts = int(state.get("attempts", 0) or 0)
        if attempts >= 3:
            return "finalize"
        if decision in ("retry_players", "retry_events", "retry_teams"):
            return decision
        return "finalize"

    # Add a final deduplication step after reviewer before compile
    workflow.add_node("final_deduplicate_events", deduplicate_events_node)

    workflow.add_conditional_edges(
        "review_analysis",
        should_after_review,
        {
            "retry_players": "extract_players",
            "retry_events": "process_segments",
            "retry_teams": "identify_teams",
            "finalize": "final_deduplicate_events",
        },
    )
    # After final deduplication, proceed to compile
    workflow.add_edge("final_deduplicate_events", "compile_analysis")
    # workflow.add_edge("compile_analysis", "normalize_players")
    workflow.add_edge("compile_analysis", END)

    return workflow.compile()