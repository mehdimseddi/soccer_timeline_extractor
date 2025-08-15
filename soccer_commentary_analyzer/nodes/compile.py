# nodes/compile.py
"""
Final compilation of all extracted data into structured analysis.
"""
from ..state_type.types_utils import CommentaryState
from ..models.schemas import FootballEvent
from ..utils.db_operations import save_analysis_to_database
from datetime import datetime
import re
from ..config import logger
from ..utils.arabic import normalize_arabic_text


def compile_analysis_node(state: CommentaryState) -> CommentaryState:
    """
    Compile final structured analysis:
    - Sort events chronologically
    - Enhance with team info from player mapping
    - Final cleanup
    """
    def parse_time(event: FootballEvent) -> float:
        t = event.time.lower()
        if t in ["ht", "halftime"]: return 46.0
        if t in ["ft", "fulltime"]: return 91.0
        # Match either "45" or "45+2" etc.
        if re.fullmatch(r"\d+", t):
            return float(t)
        elif re.fullmatch(r"\d+\+\d+", t):
            base, extra = map(int, t.split("+"))
            return float(base) + float(extra) / 60

        # Ignore invalid formats by returning a high fallback value (to push them to the end or filter out)
        return 1000.0

    valid_time_pattern = re.compile(r"^\d+$|^\d+\+\d+$|^(ht|halftime|ft|fulltime)$", re.IGNORECASE)
    # Filter out invalid events
    invalid_events_count = 0
    valid_events = []
    for e in state["extracted_events"]:
        if valid_time_pattern.match(e.time.strip()):
            valid_events.append(e)
        else:
            invalid_events_count += 1

    # Sort events
    sorted_events = sorted(valid_events, key=parse_time)

    # Build player-to-team map for inference
    player_team_map = {p.name: p.team for p in state["extracted_players"] if p.team}

    # Enhance events
    enhanced_events = []
    for event in sorted_events:
        if event.player and not event.team and event.player in player_team_map:
            event.team = player_team_map[event.player]
        enhanced_events.append(event)

    # Deduplicate final players list by normalized (name, team)
    final_players = state["extracted_players"]
    seen_keys = set()
    deduped_players = []
    for p in final_players:
        norm_name = " ".join(normalize_arabic_text((p.name or "")).lower().split())
        norm_team = (p.team or "").strip()
        key = (norm_name, norm_team)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        # ✅ Ensure player's number is numeric, otherwise set to None
        if getattr(p, "number", None) is not None:
            try:
                # Accept both int and strings that represent ints
                p.number = str(int(p.number)) 
            except (ValueError, TypeError):
                p.number = None
        deduped_players.append(p)

    try:
        logger.info(
            "Compile: invalid_time_filtered=%d final_events=%d final_players=%d",
            invalid_events_count, len(enhanced_events), len(deduped_players)
        )
    except Exception:
        pass

    # === 🔽 Save to Database Here ===
    home_team = state["teams"]["home_team"]
    away_team = state["teams"]["away_team"]

    if not home_team or not away_team:
        logger.warning("Cannot save to database: Home or away team not identified.")
    else:
        try:
            match_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            save_analysis_to_database(
                home_team_name=home_team,
                away_team_name=away_team,
                match_date=match_date,
                events=enhanced_events,
                players=deduped_players
            )
            logger.info(f"Match saved to database: {home_team} vs {away_team}")
        except Exception as e:
            logger.error(f"Failed to save match to database: {e}")
    # === 🔼 End of DB Save ===

    return {
        **state,
        "final_analysis": {
            "events": enhanced_events,
            "players": deduped_players
        }
    }