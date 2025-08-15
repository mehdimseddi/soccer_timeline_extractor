from ..state_type.types_utils import CommentaryState
from ..config import logger
def deduplicate_events_node(state: CommentaryState) -> CommentaryState:
    """Remove duplicate events based on time, type, and player"""
    events = state["extracted_events"]
    seen = set()
    unique_events = []

    logger.info(f"Deduplicating {len(events)} events...")
    for event in events:
        # Create a deduplication key
        player_key = event.player or event.player_in or event.player_out or "N/A"
        team_key = event.team or "N/A"
        key = (event.time.strip(), event.type, player_key, team_key)

        if key not in seen:
            seen.add(key)
            unique_events.append(event)
        else:
            logger.warning(f"DUPLICATE EVENT REMOVED: [{event.time}] {event.type} by {player_key}")

    logger.info(f"Deduplicated events: {len(events)} → {len(unique_events)} (removed={len(events)-len(unique_events)})")
    state["extracted_events"] = unique_events
    return state