# nodes/team_identification.py
from langchain_google_genai import ChatGoogleGenerativeAI
from ..config import DATABASE_PATH, MAX_RETRIES, logger, get_gemini_llm
from ..models.schemas import TeamIdentificationResult
from ..prompts.team_identification import TEAM_IDENTIFICATION_PROMPT
from ..state_type.types_utils import CommentaryState
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_core.exceptions import OutputParserException
import time
from ..utils.usage import ensure_usage


def identify_teams_node(state: CommentaryState) -> CommentaryState:
    """Identify home and away teams from match commentary."""
    if not state.get("cleaned_commentary"):
        logger.warning("No cleaned commentary present; skipping team identification")
        state["teams"] = {
            "home_team": "Unknown",
            "away_team": "Unknown",
            "confidence": 0.0
        }
        return state

    commentary = state["cleaned_commentary"]
    llm = get_gemini_llm(temperature=0.1)

    # Split commentary for large matches, smaller chunks than player extraction
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=8000,
        chunk_overlap=500,
        length_function=len,
        is_separator_regex=False,
    )
    chunks = text_splitter.create_documents([commentary])
    logger.info("Team identification: chunks=%d", len(chunks))

    home_team, away_team = None, None
    confidence_sum = 0
    chunks_processed = 0

    for i, chunk in enumerate(chunks):
        logger.info(f"Identifying teams: chunk {i+1}/{len(chunks)}")

        structured_llm = llm.with_structured_output(TeamIdentificationResult).with_retry(
            retry_if_exception_type=(Exception,),
            stop_after_attempt=MAX_RETRIES,
            wait_exponential_jitter=True
        )
        chain = TEAM_IDENTIFICATION_PROMPT | structured_llm

        for attempt in range(MAX_RETRIES):
            try:
                result = chain.invoke({
                    "commentary": chunk.page_content,
                    "predefined_teams": state.get("predefined_teams", [])
                })

                # Handle empty or partial results
                if not result or (not result.home_team and not result.away_team):
                    raise OutputParserException("No valid teams extracted")

                # Usage tracking
                state.setdefault("usage", ensure_usage(state))
                state["usage"]["estimated_input_tokens"] += max(1, len(chunk.page_content) // 4)
                output_len = len(result.home_team or "") + len(result.away_team or "")
                state["usage"]["estimated_output_tokens"] += max(0, output_len // 4)
                state["usage"]["llm_calls"] += 1

                if result.home_team and not home_team:
                    home_team = result.home_team
                if result.away_team and not away_team:
                    away_team = result.away_team
                confidence_sum += result.confidence or 0
                chunks_processed += 1

                break  # success for this chunk

            except OutputParserException as e:
                logger.warning(f"Parse error on chunk {i+1}, attempt {attempt+1}: {str(e)}")
                if attempt == MAX_RETRIES - 1:
                    logger.error("Failed to parse team output after max retries")
            except Exception as e:
                logger.error(f"Gemini API error on chunk {i+1}, attempt {attempt+1}: {str(e)}")
                if attempt == MAX_RETRIES - 1:
                    logger.error("Max retries reached. Skipping chunk.")

            # Light rate-limiting to avoid hitting 5 req/min free-tier limit
            time.sleep(1.5)

    # Fallback: simple DB keyword search if no teams identified
    if not home_team or not away_team:
        logger.warning("No teams identified by LLM; running fallback keyword search")
        from ..utils.db_utils import get_all_team_names
        all_known_teams = get_all_team_names(DATABASE_PATH)
        matches = [t for t in all_known_teams if t in commentary]
        if matches:
            if not home_team:
                home_team = matches[0]
            if not away_team and len(matches) > 1:
                away_team = matches[1]

    # Final assignment
    state["teams"] = {
        "home_team": home_team or "Unknown",
        "away_team": away_team or "Unknown",
        "confidence": (confidence_sum / chunks_processed) if chunks_processed else 0.0
    }

    logger.info(f"Identified teams: {state['teams']['home_team']} vs {state['teams']['away_team']}")
    return state
