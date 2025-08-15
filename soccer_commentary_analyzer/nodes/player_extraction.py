# nodes/processing.py
from langchain_google_genai import ChatGoogleGenerativeAI
from ..models.schemas import LineupResult
from ..prompts.lineup import LINEUP_PROMPT
from ..state_type.types_utils import CommentaryState
from langchain.text_splitter import RecursiveCharacterTextSplitter
from ..config import DATABASE_PATH, MAX_RETRIES, logger, get_gemini_llm, DISALLOWED_TEAM_NAMES
from ..utils.usage import ensure_usage
from langchain_core.exceptions import OutputParserException
import time  # For optional sleep between retries



def player_extraction_node(state: CommentaryState) -> CommentaryState:
    if not state.get("cleaned_commentary"):
        logger.warning("No cleaned commentary present; skipping player extraction")
        return {**state, "extracted_players": []}
    if not state.get("teams"):
        logger.warning("Teams not identified; player extraction may be less accurate")
        
    all_players = []

    team_context = f"Teams: {state['teams']['home_team']} vs {state['teams']['away_team']}"
    
    llm = get_gemini_llm(temperature=0.1)

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
    logger.info("Player extraction: chunks=%d", len(chunks))
    for i, chunk in enumerate(chunks):
        logger.info(f"Extracting players: chunk {i+1}/{len(chunks)}")
        # Format past events to include in context
        if all_players:
            past_players_lines = []
            for p in all_players:
                name = p.name or "?"
                team = p.team or "Unknown team"
                number = p.number or "Unknown number"
                position = p.position or "Unknown position"
                past_players_lines.append(f"- {name} has number {number} and position {position} plays for {team}")
            # limit to last 20 players to avoid prompt bloat
            past_players_context = "\n".join(past_players_lines[-20:])
        else:
            past_players_context = "None (this is the first segment)."

        chain = LINEUP_PROMPT | llm.with_structured_output(LineupResult).with_retry(
            retry_if_exception_type=(Exception,), stop_after_attempt=MAX_RETRIES, wait_exponential_jitter=True
        )
        # Retry logic for API calls
        for attempt in range(MAX_RETRIES):
            try:
                result = chain.invoke({
                    "segment_content": chunk.page_content,
                    "team_context": team_context,
                    "past_players_context": past_players_context,
                })
                # Rough usage accounting
                state.setdefault("usage", ensure_usage(state))
                prompt_chars = len(chunk.page_content) + len(team_context) + len(past_players_context) 
                # Assume small output for players; estimate by names length
                output_chars = sum(len(getattr(p, 'name', '') or '') for p in getattr(result, 'players', []) or [])
                state["usage"]["estimated_input_tokens"] += max(1, int(prompt_chars/4))
                state["usage"]["estimated_output_tokens"] += max(0, int(output_chars/4))
                state["usage"]["llm_calls"] += 1

                if hasattr(result, "players") and result.players:
                    # Remove obvious non-players or duplicates early
                    unique_keys = set((p.name, p.team) for p in all_players)
                    cleaned = []
                    raw_cnt = len(result.players)
                    dedup_removed = 0
                    for p in result.players:
                        logger.info(f"Processing player: {p}")
                        if not p.name or any(bad in p.name for bad in ["مدرب", "حكم", "طاقم"]):
                            continue
                        # Map team_code -> concrete team names and clamp to home/away only
                        try:
                            if getattr(p, 'team_code', None):
                                if p.team_code == 'home':
                                    p.team = state['teams']['home_team']
                                elif p.team_code == 'away':
                                    p.team = state['teams']['away_team']
                        except Exception:
                            pass
                        # If team is outside allowed set, blank it
                        try:
                            allowed = {state['teams']['home_team'], state['teams']['away_team']}
                            if p.team and p.team not in allowed:
                                p.team = None
                        except Exception:
                            pass
                        key = (p.name, p.team)
                        if key in unique_keys:
                            dedup_removed += 1
                            continue
                        unique_keys.add(key)
                        cleaned.append(p)
                    if cleaned:
                        logger.info(f"Chunk {i+1}/{len(chunks)} players: raw=%d kept=%d dedup_removed=%d", raw_cnt, len(cleaned), dedup_removed)
                        all_players.extend(cleaned)
                break  # Success → exit retry loop

            except OutputParserException as e:
                logger.warning(f"Parse error on chunk {i+1}, attempt {attempt+1}: {str(e)}")
                if attempt == 2:
                    logger.error(f"Failed to parse player output after 3 attempts. Skipping chunk.")
            except Exception as e:
                logger.error(f"Gemini API error on chunk {i+1}, attempt {attempt+1}: {str(e)}")
                if attempt == 2:
                    logger.error("Max retries reached. Using empty player list for this chunk.")

    # Fallback: if no players extracted at all, attempt a light heuristic harvest of likely player mentions
    if not all_players:
        import re
        from rapidfuzz import process, fuzz
        from ..utils.db_utils import get_all_player_names
        from ..models.schemas import PlayerInfo

        logger.warning("No starters extracted; running fallback name harvest")
        # Candidate tokenization: sequences of 2–3 Arabic words
        tokens = re.findall(r"[\u0621-\u064A]{2,}(?:\s+[\u0621-\u064A]{2,}){1,2}", commentary)
        # Filter obvious non-name patterns
        ban_substrings = ("الرابطه", "المحترفه", "كره", "قدم", "قناه", "مباراه", "الحكم", "حكم", "مدرب")
        candidates = [t.strip() for t in tokens if not any(b in t for b in ban_substrings)]

        # Score against canonical DB names; keep high-confidence matches only
        canonical = get_all_player_names(DATABASE_PATH)
        seen_names = set()
        harvested: list[PlayerInfo] = []
        for cand in candidates:
            match = process.extractOne(cand, canonical, scorer=fuzz.WRatio, score_cutoff=92)
            if not match:
                continue
            best_name, score = match[0], match[1]
            if best_name in seen_names:
                continue
            seen_names.add(best_name)
            harvested.append(PlayerInfo(name=best_name, team=None, number=None, position="unknown"))
            if len(harvested) >= 30:  # cap to avoid prompt bloat downstream
                break
        all_players.extend(harvested)
        logger.info(f"Fallback harvested {len(harvested)} canonical player names")

    return {**state, "extracted_players": all_players}