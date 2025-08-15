# nodes/validation.py
"""
Validation node to check consistency of extracted data.
"""
from ..state_type.types_utils import CommentaryState
from ..utils.arabic import display_arabic
from ..config import logger, DISALLOWED_TEAM_NAMES


def validate_analysis_node(state: CommentaryState) -> CommentaryState:
    """
    Validate extracted information for consistency:
    - Invalid team names (e.g., coach names)
    - Missing events
    - Chronological order
    - Team-player alignment
    """
    issues = []
    valid_team_keywords = ["النادي", "الترجي", "الصفاقسي", "الافريقي", "بنزرتي", "تونسي", "الرياضي"]

    # 1. Check for invalid team names (likely coach/person names)
    invalid_team_names = []
    for player in state.get("extracted_players", []):
        if player.team:
            is_valid = any(keyword in player.team for keyword in valid_team_keywords)
            if (not is_valid and player.team not in state["teams"]["all_teams"]) or (player.team in DISALLOWED_TEAM_NAMES):
                invalid_team_names.append(player.team)

    if invalid_team_names:
        issues.append(f"Found invalid team names that appear to be person names: {', '.join(invalid_team_names)}. Remember: Coach names like 'فوزي بنزرتي' are NOT team names.")


    # 2. Check if any events were extracted
    no_events_flag = False
    subs_incomplete = 0
    missing_player = 0
    if not state.get("extracted_events"):
        no_events_flag = True
        issues.append("No match events were extracted. This is unusual for soccer commentary.")
    else:
        # Sanity checks on events: plausible times and substitution integrity
        for ev in state["extracted_events"]:
            if ev.type == "substitution" and (not ev.player_out or not ev.player_in):
                subs_incomplete += 1
                issues.append(f"Substitution at {ev.time} missing player_in/player_out")
            # Enforce player presence for non-substitution events
            if ev.type != "substitution" and not ev.player:
                missing_player += 1
                issues.append(f"Event at {ev.time} is missing player (players are required for all events)")

    # 3. Try to infer team from player-team mapping (auto-fix; only flag when ambiguous)
    player_team_map = {p.name: p.team for p in state["extracted_players"] if p.team}
    for event in state["extracted_events"]:
        if event.player and not event.team:
            if event.player in player_team_map:
                event.team = player_team_map[event.player]
            else:
                # Check across teams for ambiguous player (rare when roster normalized)
                issues.append(f"Event at {event.time} has player '{event.player}' but no team information")

    # 3b. Global consistency: events with zero detected players
    if state.get("extracted_events") and not state.get("extracted_players"):
        issues.append("Events exist but zero players detected in lineup — attempting player fallback in next pass.")

    # 4. Validate chronological order
    def parse_time(event):
        t = event.time.lower()
        if t in ["ht", "halftime"]: return 46.0
        if t in ["ft", "fulltime"]: return 91.0
        if "+" in t:
            base, extra = t.split("+")
            return float(base) + float(extra)/60
        try: return float(t)
        except: return 100.0

    try:
        sorted_events = sorted(state["extracted_events"], key=parse_time)
        for i in range(1, len(sorted_events)):
            if parse_time(sorted_events[i]) < parse_time(sorted_events[i-1]):
                issues.append(f"Event at {sorted_events[i].time} appears to be out of chronological order")
    except Exception as e:
        issues.append(f"Could not validate chronological order: {str(e)}")

    # Summarize key issue counts for observability
    try:
        logger.info(
            "Validation issues: total=%d (invalid_team=%d, no_events=%d, subs_incomplete=%d, missing_player=%d)",
            len(issues), len(invalid_team_names), 1 if no_events_flag else 0, subs_incomplete, missing_player
        )
    except Exception:
        pass
    return {
        **state,
        "validation_issues": issues,
        "attempts": state.get("attempts", 0) + 1
    }