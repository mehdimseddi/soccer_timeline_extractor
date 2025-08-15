from ..state_type.types_utils import CommentaryState
from rapidfuzz import fuzz
from ..config import logger, DB_MATCH_THRESHOLD, AUTO_AUGMENT_ROSTER, MAX_AUTO_AUGMENT, MIN_CONFIDENCE_TO_KEEP_UNRESOLVED, STRICT_ROSTER_ENFORCEMENT
from ..utils.metrics import metrics
from ..utils.db_utils import find_best_player_match, get_all_player_names
from ..models.schemas import PlayerInfo

def sync_events_with_final_players_node(state: CommentaryState) -> CommentaryState:
    """
    Reconcile event players with the final, validated player list.
    Ensures:
    - Only players from the final roster appear in events
    - Player names in events use canonical names
    - Teams in events are consistent with final roster
    """
    final_players = state["extracted_players"]  # After normalization & composition
    events = state["extracted_events"]
    
    # Track metrics
    unresolved_at_sync_start = 0
    resolved_by_roster = 0
    resolved_by_db_match = 0
    auto_augmented_players = 0
    kept_for_reviewer = 0
    dropped_unresolved_final = 0

    # Build canonical lookup: raw-like name → final canonical name + team
    name_to_final = {}
    for p in final_players:
        # Normalize variations (exact + common typos)
        key = p.name.strip().lower()
        name_to_final[key] = {
            "canonical_name": p.name,
            "team": p.team
        }

    updated_events = []
    final_players_list = list(final_players)  # Make a copy we can modify if needed
    
    for event in events:
        changed = False
        updated_event = event
        
        # Track if this event was originally unresolved
        was_unresolved = False
        if hasattr(event, '_unresolved'):
            was_unresolved = event._unresolved

        # Helper to safely resolve player name with multiple fallback strategies
        def resolve_player(name: str, team_hint: str = None):
            nonlocal resolved_by_roster, resolved_by_db_match, auto_augmented_players
            
            if not name:
                return None
            key = name.strip().lower()
            
            # 1. Try current roster mapping (exact match)
            if key in name_to_final:
                final_info = name_to_final[key]
                if key != name:  # Different capitalization or spacing
                    logger.info(f"Syncing event player: '{name}' → '{final_info['canonical_name']}'")
                resolved_by_roster += 1
                return final_info
            
            # 2. Try fuzzy fallback within final roster only
            for final_key, info in name_to_final.items():
                if fuzz.ratio(key, final_key) > 90:
                    logger.info(f"Fuzzy-syncing event player: '{name}' → '{info['canonical_name']}'")
                    resolved_by_roster += 1
                    return info
            
            # 3. If not found in roster, try DB fuzzy match with team hints
            if not STRICT_ROSTER_ENFORCEMENT:
                try:
                    best, score = find_best_player_match(
                        name, 
                        get_all_player_names(), 
                        threshold=DB_MATCH_THRESHOLD, 
                        team_hint=team_hint
                    )
                    if best and score >= DB_MATCH_THRESHOLD:
                        logger.info(f"DB-match syncing event player: '{name}' → '{best}' (score: {score})")
                        resolved_by_db_match += 1
                        
                        # Option B: auto-augment roster if enabled
                        if AUTO_AUGMENT_ROSTER and auto_augmented_players < MAX_AUTO_AUGMENT:
                            # Add to final players if not already there
                            existing_player = next((p for p in final_players_list if p.name == best), None)
                            if not existing_player:
                                # We need team info to add player - try to infer from event or team_hint
                                inferred_team = team_hint or getattr(event, 'team', None)
                                if inferred_team:
                                    new_player = PlayerInfo(
                                        name=best, 
                                        team=inferred_team, 
                                        number=None, 
                                        position="unknown"
                                    )
                                    final_players_list.append(new_player)
                                    # Update name_to_final for future lookups
                                    new_key = best.strip().lower()
                                    name_to_final[new_key] = {
                                        "canonical_name": best,
                                        "team": inferred_team
                                    }
                                    auto_augmented_players += 1
                                    logger.info(f"Auto-augmented roster with player: '{best}' (team: {inferred_team})")
                        
                        return {"canonical_name": best, "team": team_hint}
                except Exception as e:
                    logger.debug(f"DB match failed for player '{name}': {e}")
            
            return None

        # Update player fields
        if event.player:
            team_hint = getattr(event, 'team', None)
            resolved = resolve_player(event.player, team_hint)
            if resolved:
                if event.player != resolved["canonical_name"]:
                    updated_event = updated_event.model_copy(update={"player": resolved["canonical_name"]})
                    changed = True
                if not event.team and resolved["team"]:
                    updated_event = updated_event.model_copy(update={"team": resolved["team"]})
                    changed = True
            else:
                # Keep event if confidence is high enough and team is known
                if (getattr(event, 'confidence', 0.0) >= MIN_CONFIDENCE_TO_KEEP_UNRESOLVED and 
                    (event.team or team_hint) and not STRICT_ROSTER_ENFORCEMENT):
                    kept_for_reviewer += 1
                    logger.info(f"Keeping unresolved event: player '{event.player}' @ {event.time} (confidence: {event.confidence})")
                    # Add a marker so reviewer knows this was unresolved
                    updated_event = updated_event.model_copy(update={"_unresolved": True})
                else:
                    # Drop if confidence too low or no team info
                    logger.warning(f"Dropping event: player '{event.player}' NOT resolvable and confidence too low or no team")
                    dropped_unresolved_final += 1
                    continue

        if event.type == "substitution":
            team_hint = getattr(event, 'team', None)
            
            if event.player_in:
                resolved = resolve_player(event.player_in, team_hint)
                if resolved:
                    if event.player_in != resolved["canonical_name"]:
                        updated_event = updated_event.model_copy(update={"player_in": resolved["canonical_name"]})
                        changed = True
                    if not event.team and resolved["team"]:
                        updated_event = updated_event.model_copy(update={"team": resolved["team"]})
                        changed = True
                else:
                    # For substitutions, we're more lenient - keep partial information
                    if not STRICT_ROSTER_ENFORCEMENT:
                        kept_for_reviewer += 1
                        updated_event = updated_event.model_copy(update={"_unresolved": True})
                    else:
                        logger.warning(f"Dropping substitution: IN '{event.player_in}' NOT resolvable")
                        dropped_unresolved_final += 1
                        continue
                        
            if event.player_out:
                resolved = resolve_player(event.player_out, team_hint)
                if resolved:
                    if event.player_out != resolved["canonical_name"]:
                        updated_event = updated_event.model_copy(update={"player_out": resolved["canonical_name"]})
                        changed = True
                    if not event.team and resolved["team"]:
                        updated_event = updated_event.model_copy(update={"team": resolved["team"]})
                        changed = True
                else:
                    # For substitutions, we're more lenient - keep partial information
                    if not STRICT_ROSTER_ENFORCEMENT:
                        kept_for_reviewer += 1
                        updated_event = updated_event.model_copy(update={"_unresolved": True})
                    else:
                        logger.warning(f"Dropping substitution: OUT '{event.player_out}' NOT resolvable")
                        dropped_unresolved_final += 1
                        continue

        updated_events.append(updated_event)
        if changed:
            logger.info(f"Updated event: [{event.time}] {event.type}")

    # Replace events and update players if we augmented the roster
    state["extracted_events"] = updated_events
    if AUTO_AUGMENT_ROSTER and auto_augmented_players > 0:
        state["extracted_players"] = final_players_list
    
    # Emit metrics
    try:
        metrics.emit("player_resolution_summary", {
            "resolved_by_roster": resolved_by_roster,
            "resolved_by_db_match": resolved_by_db_match,
            "auto_augmented_players": auto_augmented_players,
            "kept_for_reviewer": kept_for_reviewer,
            "dropped_unresolved_final": dropped_unresolved_final
        })
    except Exception:
        pass
        
    try:
        logger.info(
            "Event sync: resolved_by_roster=%d resolved_by_db_match=%d auto_augmented=%d kept_for_reviewer=%d dropped=%d final_events=%d", 
            resolved_by_roster, resolved_by_db_match, auto_augmented_players, kept_for_reviewer, dropped_unresolved_final, len(updated_events)
        )
    except Exception:
        pass
        
    return state