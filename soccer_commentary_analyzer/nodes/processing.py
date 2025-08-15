# nodes/processing.py
from langchain_google_genai import ChatGoogleGenerativeAI
from ..models.schemas import  EventsResult
from ..prompts.events import EVENTS_PROMPT
from ..state_type.types_utils import CommentaryState
from collections import defaultdict
from langchain.text_splitter import RecursiveCharacterTextSplitter
from ..config import  MAX_RETRIES, STRICT_ROSTER_ENFORCEMENT, logger, get_gemini_llm, EVENT_CONFIDENCE_THRESHOLD, DISALLOWED_TEAM_NAMES
from ..utils.arabic import normalize_arabic_text
from ..utils.metrics import metrics
from ..utils.usage import ensure_usage
import time  # For optional sleep between retries
from langchain_core.exceptions import OutputParserException


def process_segments_node(state: CommentaryState) -> CommentaryState:
    if not state.get("cleaned_commentary"):
        logger.warning("No cleaned commentary present; skipping event extraction")
        return {**state, "extracted_events": []}
    if not state.get("teams"):
        logger.warning("Teams not identified; event extraction may be less accurate")
        
    llm = get_gemini_llm(temperature=0.1)

    all_events = []
    # Buffer for partial substitutions to pair across adjacent chunks
    partial_sub_buffer = []

    team_context = f"Teams: {state['teams']['home_team']} vs {state['teams']['away_team']}"
    
    player_context = ""
    extracted_players = state.get("extracted_players", [])
    team_players = defaultdict(list)
    for player in extracted_players:
        if player.team:
            team_players[player.team].append(player)
    for team, players in team_players.items():
        # limit to first 15 names to avoid prompt bloat
        limited = ", ".join(p.name for p in players[:15])
        player_context += f"{team} with {len(players)} players: {limited}\n"
    # print(f"Player context: {player_context}")

    commentary = state["cleaned_commentary"]
     # Initialize text splitter
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=10000,  # Adjust based on your needs
        chunk_overlap=1000,
        length_function=len,
        is_separator_regex=False,
    )

    # Split into chunks
    chunks = text_splitter.create_documents([commentary])
    logger.info("Event extraction: chunks=%d roster_players=%d", len(chunks), sum(len(v) for v in team_players.values()))
    logger.info("Player context: %s", player_context.strip())  
    for i, chunk in enumerate(chunks):
        logger.info(f"Extracting events: chunk {i+1}/{len(chunks)}")
        # Format past events to include in context
        if all_events:
            past_events_lines = []
            for ev in all_events:
                time = ev.time or "?"
                player = ev.player or ev.player_out or ev.player_in or "Unknown"
                team = ev.team or "Unknown team"
                past_events_lines.append(f"- {ev.type} by {player} for {team} at {time}")
            past_events_context = "\n".join(past_events_lines)
        else:
            past_events_context = "None (this is the first segment)."

        # Dynamic constraints fed back from earlier validations + disallowed team names
        issues = state.get("validation_issues", []) or []
        dynamic_constraints = ("\n".join(f"• {msg}" for msg in issues) + "\n") if issues else ""
        if DISALLOWED_TEAM_NAMES:
            dynamic_constraints += (
                "⛔ لا تستعمل هذه الأسماء كأسماء فرق (مدربين/أشخاص): " + ", ".join(DISALLOWED_TEAM_NAMES)
            )

        chain = EVENTS_PROMPT | llm.with_structured_output(EventsResult).with_retry(retry_if_exception_type=(Exception,), 
                                                                                    stop_after_attempt=MAX_RETRIES, 
                                                                                    wait_exponential_jitter=True
                                                                                    )

        # Build a fast lookup of valid player names from roster, normalized (Arabic)
        def _norm(text: str) -> str:
            try:
                return " ".join(normalize_arabic_text((text or "")).lower().split())
            except Exception:
                return (text or "").strip().lower()

        valid_player_names = {p.name for roster in team_players.values() for p in roster if getattr(p, 'name', None)}
        normalized_valid_names = {_norm(name) for name in valid_player_names}
        roster_is_empty = (len(normalized_valid_names) == 0)
        # Map normalized player name -> teams they belong to (for team inference)
        name_to_teams: dict[str, set[str]] = {}
        for team, roster in team_players.items():
            for p in roster:
                if getattr(p, 'name', None):
                    key = _norm(p.name)
                    name_to_teams.setdefault(key, set()).add(team)

        # Retry logic for API calls
        for attempt in range(MAX_RETRIES):
            try:
                result = chain.invoke({
                    "segment_content": chunk.page_content,
                "team_context": team_context,
                "player_roster_context": player_context,
                "past_events_context": past_events_context,
                "dynamic_constraints": dynamic_constraints,
                })
                # Rough usage counters based on prompt and output sizes
                state.setdefault("usage", ensure_usage(state))
                prompt_chars = len(chunk.page_content) + len(team_context) + len(player_context) + len(past_events_context) + len(dynamic_constraints)
                output_chars = sum(len(getattr(ev, 'details', '') or '') for ev in getattr(result, 'events', []) or [])
                state["usage"]["estimated_input_tokens"] += max(1, int(prompt_chars/4))
                state["usage"]["estimated_output_tokens"] += max(0, int(output_chars/4))
                state["usage"]["llm_calls"] += 1

                if hasattr(result, "events") and result.events:
                    # Confidence filtering and minimal validation
                    filtered = []
                    dropped_low_conf = 0
                    dropped_no_player = 0
                    kept_not_in_roster = 0  # Changed from dropped_not_in_roster
                    buffered_partial = 0
                    for ev in result.events:
                        if getattr(ev, 'confidence', 0.0) < EVENT_CONFIDENCE_THRESHOLD:
                            dropped_low_conf += 1
                            continue
                        # Enforce: every non-substitution event must have a player
                        if ev.type != 'substitution' and not ev.player:
                            dropped_no_player += 1
                            continue
                        # NEW POLICY: Keep events with players not in roster instead of dropping them immediately
                        # Only enforce strict roster when STRICT_ROSTER_ENFORCEMENT is true
                        if ev.type != 'substitution' and ev.player and normalized_valid_names and not roster_is_empty:
                            if _norm(ev.player) not in normalized_valid_names:
                                if not STRICT_ROSTER_ENFORCEMENT:
                                    # Keep event but lower confidence and mark as unresolved
                                    ev.confidence = min(ev.confidence, 0.6)
                                    # Add to unresolved tracking in state
                                    state.setdefault("unresolved_event_players", set()).add(_norm(ev.player))
                                    kept_not_in_roster += 1
                                    logger.info(f"Keeping event with player not in roster @ {ev.time}: {ev.player} (confidence reduced to {ev.confidence})")
                                else:
                                    # Old behavior: drop if strict enforcement
                                    logger.warning(f"Dropping event with player not in roster @ {ev.time}: {ev.player}")
                                    dropped_not_in_roster += 1
                                    continue
                        # Ensure substitution completeness
                        if ev.type == 'substitution' and (not ev.player_out or not ev.player_in):
                            # Buffer partial substitution for pairing with adjacent chunk events
                            partial_sub_buffer.append({
                                "time": ev.time,
                                "player_out": ev.player_out,
                                "player_in": ev.player_in,
                                "team": ev.team,
                            })
                            buffered_partial += 1
                            continue
                        # For substitutions, handle players not in roster with new policy
                        substitution_handled = True
                        if ev.type == 'substitution' and normalized_valid_names and not roster_is_empty:
                            out_not_in_roster = ev.player_out and _norm(ev.player_out) not in normalized_valid_names
                            in_not_in_roster = ev.player_in and _norm(ev.player_in) not in normalized_valid_names
                            
                            if (out_not_in_roster or in_not_in_roster) and not STRICT_ROSTER_ENFORCEMENT:
                                # Keep substitution event but mark players as unresolved
                                if out_not_in_roster:
                                    state.setdefault("unresolved_event_players", set()).add(_norm(ev.player_out))
                                if in_not_in_roster:
                                    state.setdefault("unresolved_event_players", set()).add(_norm(ev.player_in))
                                # Lower confidence if needed
                                ev.confidence = min(ev.confidence, 0.6)
                                kept_not_in_roster += 1
                                logger.info(f"Keeping substitution with players not in roster @ {ev.time}: out={ev.player_out}, in={ev.player_in} (confidence reduced to {ev.confidence})")
                            elif (out_not_in_roster or in_not_in_roster) and STRICT_ROSTER_ENFORCEMENT:
                                # Old behavior: drop if strict enforcement
                                logger.debug(f"Dropping substitution with players not in roster @ {ev.time}: out={ev.player_out}, in={ev.player_in}")
                                substitution_handled = False
                                continue
                        # Auto-infer team if player is known in roster and team missing (only if unambiguous)
                        if ev.player and not ev.team:
                            teams_for_player = list(name_to_teams.get(_norm(ev.player), []))
                            if len(teams_for_player) == 1:
                                ev.team = teams_for_player[0]
                        filtered.append(ev)
                    if filtered:
                        logger.info(f"Extracted {len(filtered)} events from chunk {i+1}")
                        all_events.extend(filtered)
                    # Try to pair buffered partial substitutions with newly extracted events
                    if partial_sub_buffer and 'filtered' in locals() and filtered:
                        resolved_parts = []
                        for part in partial_sub_buffer:
                            paired = False
                            for ev in filtered:
                                if ev.type != 'substitution':
                                    continue
                                # Fill complementary field if missing
                                if part.get("player_out") and not ev.player_out and ev.player_in:
                                    ev.player_out = part["player_out"]
                                    if not ev.team and part.get("team"):
                                        ev.team = part["team"]
                                    paired = True
                                    break
                                if part.get("player_in") and not ev.player_in and ev.player_out:
                                    ev.player_in = part["player_in"]
                                    if not ev.team and part.get("team"):
                                        ev.team = part["team"]
                                    paired = True
                                    break
                            if paired:
                                resolved_parts.append(part)
                                logger.info(f"Paired partial substitution at {part['time']}")
                        if resolved_parts:
                            partial_sub_buffer = [p for p in partial_sub_buffer if p not in resolved_parts]
                    try:
                        logger.info(
                            "Chunk %d/%d events: kept=%d dropped_low_conf=%d dropped_no_player=%d kept_not_in_roster=%d buffered_partial=%d",
                            i+1, len(chunks), len(filtered), dropped_low_conf, dropped_no_player, kept_not_in_roster, buffered_partial
                        )
                    except Exception:
                        pass
                break  # Success → exit retry loop

            except OutputParserException as e:
                logger.warning(f"Parse error on chunk {i+1}, attempt {attempt+1}: {str(e)}")
                if attempt == 2:
                    logger.error(f"Failed to parse player output after 3 attempts. Skipping chunk.")
            except Exception as e:
                logger.error(f"Gemini API error on chunk {i+1}, attempt {attempt+1}: {str(e)}")
                if attempt == 2:
                    logger.error("Max retries reached. Using empty player list for this chunk.")     
    # Emit simple instrumentation summary
    try:
        by_type = {}
        for ev in all_events:
            by_type[ev.type] = by_type.get(ev.type, 0) + 1
        metrics.emit("event_extraction_summary", {
            "total_events": len(all_events),
            "by_type": by_type,
            "remaining_partial_subs": len(partial_sub_buffer),
        })
    except Exception:
        pass

    return {**state, "extracted_events": all_events}