from ..config import DATABASE_PATH
from ..utils.db_utils import (
    get_all_player_names,
    get_canonical_player_name,
    find_best_player_match,
    get_possible_teams_for_player
)
from ..utils.arabic import normalize_arabic_text
from ..config import logger
from ..state_type.types_utils import CommentaryState

def normalize_players_node(state: CommentaryState) -> CommentaryState:
    """
    Normalize extracted player names using fuzzy matching and DB lookup.
    Also corrects team assignment if possible.
    """
    canonical_names = get_all_player_names(DATABASE_PATH)
    
    normalized_players = []
    # normalized_events = []

    # Map to store resolved player -> canonical name
    name_mapping = {}

    exact_cnt = 0
    fuzzy_cnt = 0
    no_match_cnt = 0
    inferred_cnt = 0

    for player in state["extracted_players"]:
        original_name = player.name.strip()
        if not original_name:
            continue

        # Try exact match first
        canonical_name = get_canonical_player_name(original_name, DATABASE_PATH)
        
        if not canonical_name:
            # Fuzzy match if no exact match
            canonical_name, score = find_best_player_match(original_name, canonical_names, threshold=85, team_hint=player.team)
            if canonical_name:
                logger.info(f"Fuzzy matched '{original_name}' -> '{canonical_name}' (score: {score})")
                fuzzy_cnt += 1
        
        if canonical_name:
            # Update player with canonical name
            player.name = canonical_name
            exact_cnt += 1 if canonical_name == original_name else 0
            # Optionally update team if missing
            if not player.team:
                possible_teams = get_possible_teams_for_player(canonical_name, DATABASE_PATH)
                if len(possible_teams) == 1:
                    player.team = possible_teams[0]
                    logger.info(f"Inferred team for {canonical_name}: {possible_teams[0]}")
                    inferred_cnt += 1
            name_mapping[original_name] = canonical_name
        else:
            logger.warning(f"No canonical match found for player: {original_name}")
            name_mapping[original_name] = original_name  # fallback
            no_match_cnt += 1

        normalized_players.append(player)

    # Restrict teams strictly to identified home/away (drop others to unassigned)
    try:
        allowed_teams = set()
        if state.get("teams"):
            if state["teams"].get("home_team"): allowed_teams.add(state["teams"]["home_team"]) 
            if state["teams"].get("away_team"): allowed_teams.add(state["teams"]["away_team"]) 
        if allowed_teams:
            for p in normalized_players:
                if p.team and p.team not in allowed_teams:
                    logger.warning(f"Dropping team assignment outside match: {p.name} -> {p.team}")
                    p.team = None
    except Exception:
        pass

    # valid_player_names = {p.name for p in normalized_players} # Ensure we only keep unique names
    # print(f"Valid player names after normalization: {sorted(valid_player_names)}")

    # # Now update events with canonical player names
    # for event in state["final_analysis"]["events"]:
    #     # Handle substitution events (player_out/player_in)
    #     if event.type == "substitution":
    #         if event.player_out:
    #             event.player_out = name_mapping.get(event.player_out, event.player_out)
    #         if event.player_in:
    #             event.player_in = name_mapping.get(event.player_in, event.player_in)
    #         # Also update the generic 'player' field if present
    #         if event.player:
    #             event.player = name_mapping.get(event.player, event.player)
    #     else:
    #         # Regular events
    #         if event.player:
    #             event.player = name_mapping.get(event.player, event.player)

    #     # Optionally: re-infer team from player if missing
    #     if event.player and not event.team:
    #         possible_teams = get_possible_teams_for_player(event.player, DATABASE_PATH)
    #         if len(possible_teams) == 1:
    #             event.team = possible_teams[0]
    #             print(f"Inferred team for event player {event.player}: {possible_teams[0]}")

    #     normalized_events.append(event)

    # Update final analysis
    updated_final = {
        # "events": normalized_events,
        "players": normalized_players
    }

    try:
        logger.info(
            "Normalization: exact=%d fuzzy=%d no_match=%d team_inferred=%d",
            exact_cnt, fuzzy_cnt, no_match_cnt, inferred_cnt
        )
    except Exception:
        pass
    return {**state,"extracted_players": normalized_players ,"final_analysis": updated_final}
