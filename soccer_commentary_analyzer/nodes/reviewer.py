# nodes/reviewer.py
from __future__ import annotations
from typing import List, Dict, Any, Optional, Literal

from pydantic import BaseModel, Field

from ..state_type.types_utils import CommentaryState
from langchain.text_splitter import RecursiveCharacterTextSplitter
from ..config import logger, get_gemini_llm, LLM_MODEL_LITE_NAME, MAX_RETRIES
from ..prompts.reviewer import REVIEW_PROMPT


class EventEdit(BaseModel):
    id: str = Field(..., description="event id like 'e0'")
    action: Literal["fix_player_name", "attach_team", "set_time", "drop_event"]
    to: Optional[str] = None
    evidence: Optional[str] = None


class PlayerMerge(BaseModel):
    keep: str
    merge: List[str]
    evidence: Optional[str] = None


class PlayersAdd(BaseModel):
    name: str
    team: str
    evidence: str


class EventAdd(BaseModel):
    type: str
    time: str
    team: str
    player: Optional[str] = None
    player_out: Optional[str] = None
    player_in: Optional[str] = None
    details: Optional[str] = None
    evidence: str


class Mapping(BaseModel):
    from_name: str = Field(alias="from")
    to: str
    evidence: str


class Scores(BaseModel):
    evidence_coverage: float
    roster_consistency: float
    chronology_ok: int
    rule_violations: int


class ReviewerOutput(BaseModel):
    event_edits: List[EventEdit] = Field(default_factory=list)
    player_merges: List[PlayerMerge] = Field(default_factory=list)
    players_add: List[PlayersAdd] = Field(default_factory=list)
    events_add: List[EventAdd] = Field(default_factory=list)
    mappings: List[Mapping] = Field(default_factory=list)
    drops: List[Dict[str, str]] = Field(default_factory=list)
    scores: Optional[Scores] = None


def reviewer_node(state: CommentaryState) -> CommentaryState:
    """
    LLM reviewer that diagnoses issues and proposes small, safe edits.
    Uses structured output with retries, similar to extraction nodes.
    """
    commentary = state.get("cleaned_commentary", "")
    teams = state.get("teams") or {}
    players = state.get("extracted_players", [])
    events = state.get("extracted_events", [])
    issues = state.get("validation_issues", [])

    # Pre-call observability
    try:
        logger.info(
            "Reviewer input: players=%d, events=%d, issues=%d, home=%s, away=%s",
            len(players), len(events), len(issues), teams.get("home_team", ""), teams.get("away_team", "")
        )
        logger.debug(
            "Reviewer input sizes: commentary_chars=%d",
            len(commentary or "")
        )
    except Exception as e:
        logger.warning(f"Reviewer input logging failed, skipping {e}")
        pass

    # Prepare compact lists for prompt
    players_list = "\n".join(
        f"- {p.name} | team={p.team or 'N/A'} | num={p.number or 'N/A'} | pos={p.position or 'N/A'}"
        for p in players
    )
    events_list = "\n".join(
        f"- e{i}: {ev.type} @ {ev.time} | player={getattr(ev, 'player', None) or 'N/A'} | team={ev.team or 'N/A'}"
        + (f" | in={getattr(ev, 'player_in', None)} | out={getattr(ev, 'player_out', None)}" if ev.type == 'substitution' else "")
        for i, ev in enumerate(events)
    )

    llm = get_gemini_llm(model_name=LLM_MODEL_LITE_NAME, temperature=0.1)
    chain = REVIEW_PROMPT | llm.with_structured_output(ReviewerOutput).with_retry(
        retry_if_exception_type=(Exception,),
        stop_after_attempt=MAX_RETRIES,
        wait_exponential_jitter=True,
    )

    # Chunk commentary similarly to player extraction to control prompt size
    try:
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=10000,
            chunk_overlap=1000,
            length_function=len,
            is_separator_regex=False,
        )
        docs = text_splitter.create_documents([commentary or ""])
        logger.info("Reviewer chunking: chunks=%d full_chars=%d", len(docs), len(commentary or ""))
    except Exception:
        docs = [type("Doc", (), {"page_content": commentary or ""})()]

    agg_event_edits: List[EventEdit] = []
    agg_player_merges: List[PlayerMerge] = []
    agg_players_add: List[PlayersAdd] = []
    agg_events_add: List[EventAdd] = []
    agg_mappings: List[Mapping] = []

    for ci, d in enumerate(docs):
        chunk_text = d.page_content
        try:
            res: ReviewerOutput = chain.invoke({
                "commentary": chunk_text,
                "home_team": teams.get("home_team", ""),
                "away_team": teams.get("away_team", ""),
                "players_list": players_list,
                "events_list": events_list,
                "validation_issues": "\n".join(issues)
            })
            logger.info(
                "Reviewer chunk %d/%d proposed: edits=%d merges=%d mappings=%d add_players=%d add_events=%d (chunk_chars=%d)",
                ci+1, len(docs), len(res.event_edits), len(res.player_merges), len(res.mappings), len(res.players_add), len(res.events_add), len(chunk_text or "")
            )
            agg_event_edits.extend(res.event_edits or [])
            agg_player_merges.extend(res.player_merges or [])
            agg_players_add.extend(res.players_add or [])
            agg_events_add.extend(res.events_add or [])
            agg_mappings.extend(res.mappings or [])
        except Exception as e:
            logger.warning(f"Reviewer chunk {ci+1} failed: {e}")
            continue

    try:
        result = ReviewerOutput(
            event_edits=agg_event_edits,
            player_merges=agg_player_merges,
            players_add=agg_players_add,
            events_add=agg_events_add,
            mappings=agg_mappings,
            scores=None,
        )
    except Exception as e:
        logger.warning(f"Reviewer aggregation failed: {e}")
        return state

    # Log reviewer output (summary + JSON at debug)
    try:
        import json as _json
        logger.info(
            "Reviewer proposed: edits=%d, merges=%d, mappings=%d, add_players=%d, add_events=%d",
            len(result.event_edits), len(result.player_merges), len(result.mappings), len(result.players_add), len(result.events_add)
        )
        # Show a tiny sample at debug level
        try:
            logger.debug("Reviewer sample edit: %s", (result.event_edits[:1][0].model_dump() if result.event_edits else {}))
        except Exception:
            pass
        logger.debug(
            "Reviewer output JSON: "
            + _json.dumps(result.model_dump(), ensure_ascii=False)
        )
    except Exception:
        pass

    logger.info("Reviewer: applying proposed edits")
    # Apply event edits
    updated_events: List[Any] = list(events)
    players_before = len(players)
    events_before = len(updated_events)

    def get_event_by_id(idx: int):
        return updated_events[idx] if 0 <= idx < len(updated_events) else None

    applied_event_edits = 0
    skipped_invalid_id = 0
    skipped_missing_target = 0
    skipped_missing_event = 0
    skipped_unknown_action = 0
    for edit in result.event_edits:
        try:
            if not edit.id.startswith("e"):
                skipped_invalid_id += 1
                continue
            idx = int(edit.id[1:])
            ev = get_event_by_id(idx)
            if not ev:
                skipped_missing_event += 1
                continue
            if edit.action == "fix_player_name" and edit.to:
                ev = ev.model_copy(update={"player": edit.to})
            elif edit.action == "attach_team" and edit.to:
                ev = ev.model_copy(update={"team": edit.to})
            elif edit.action == "set_time" and edit.to:
                ev = ev.model_copy(update={"time": edit.to})
            elif edit.action == "drop_event":
                updated_events.pop(idx)
                continue
            else:
                skipped_unknown_action += 1
                continue
            updated_events[idx] = ev
            applied_event_edits += 1
        except Exception:
            skipped_unknown_action += 1
            continue

    # Apply player merges (rename variants to keep)
    applied_merges = 0
    if result.player_merges:
        keep_map: Dict[str, str] = {}
        for m in result.player_merges:
            for alias in m.merge:
                if m.keep and alias and alias != m.keep:
                    keep_map[alias] = m.keep
        if keep_map:
            # Update players
            for p in players:
                if p.name in keep_map:
                    p.name = keep_map[p.name]
            # Update events
            for i, ev in enumerate(updated_events):
                if getattr(ev, 'player', None) in keep_map:
                    updated_events[i] = ev.model_copy(update={"player": keep_map[ev.player]})
                    applied_merges += 1
                if getattr(ev, 'player_in', None) in keep_map:
                    updated_events[i] = updated_events[i].model_copy(update={"player_in": keep_map[ev.player_in]})
                    applied_merges += 1
                if getattr(ev, 'player_out', None) in keep_map:
                    updated_events[i] = updated_events[i].model_copy(update={"player_out": keep_map[ev.player_out]})
                    applied_merges += 1

    # Apply mappings to players and events
    applied_mappings = 0
    if result.mappings:
        map_dict: Dict[str, str] = {m.from_name: m.to for m in result.mappings}
        for p in players:
            if p.name in map_dict:
                p.name = map_dict[p.name]
                applied_mappings += 1
        for i, ev in enumerate(updated_events):
            if getattr(ev, 'player', None) in map_dict:
                updated_events[i] = ev.model_copy(update={"player": map_dict[ev.player]})
                applied_mappings += 1
            if getattr(ev, 'player_in', None) in map_dict:
                updated_events[i] = updated_events[i].model_copy(update={"player_in": map_dict[ev.player_in]})
                applied_mappings += 1
            if getattr(ev, 'player_out', None) in map_dict:
                updated_events[i] = updated_events[i].model_copy(update={"player_out": map_dict[ev.player_out]})
                applied_mappings += 1

    # Add players/events as proposed (light guard: teams constrained upstream)
    added_players = 0
    if result.players_add:
        from ..models.schemas import PlayerInfo
        for pa in result.players_add:
            try:
                players.append(PlayerInfo(name=pa.name, team=pa.team, number=None, position="unknown"))
                added_players += 1
            except Exception:
                continue
    added_events = 0
    if result.events_add:
        from ..models.schemas import FootballEvent
        for ea in result.events_add:
            try:
                updated_events.append(FootballEvent(
                    type=ea.type,
                    player=ea.player,
                    player_out=ea.player_out,
                    player_in=ea.player_in,
                    team=ea.team,
                    time=ea.time,
                    details=ea.details or "",
                    confidence=0.7
                ))
                added_events += 1
            except Exception:
                continue

    logger.info(
        "Reviewer applied: edits=%d, merges=%d, mappings=%d, players_add=%d, events_add=%d",
        applied_event_edits, applied_merges, applied_mappings, added_players, added_events
    )
    if (skipped_invalid_id + skipped_missing_event + skipped_missing_target + skipped_unknown_action) > 0:
        logger.info(
            "Reviewer skipped: invalid_id=%d missing_event=%d missing_target=%d unknown_action=%d",
            skipped_invalid_id, skipped_missing_event, skipped_missing_target, skipped_unknown_action
        )

    # Decide whether to finalize or retry based on scores/coverage
    decision = "finalize"
    try:
        sc = result.scores
        # Heuristics: if coverage/consistency are low, request retries upstream
        if sc:
            if (sc.evidence_coverage or 0) < 0.7 or (sc.roster_consistency or 0) < 0.8:
                # What to retry first? If few players, retry players; else events.
                decision = "retry_players" if len(players) < 8 else "retry_events"
        logger.info(
            f"Reviewer scores: coverage={getattr(sc,'evidence_coverage',None)}, roster={getattr(sc,'roster_consistency',None)}, decision={decision}"
        )
    except Exception:
        pass

    state["extracted_events"] = updated_events
    state["extracted_players"] = players
    state["review_decision"] = decision

    # Delta summary
    try:
        logger.info(
            "Reviewer delta: events %d→%d, players %d→%d, decision=%s",
            events_before, len(updated_events), players_before, len(players), decision
        )
        # Log what changed: list new events compared to original
        try:
            def _event_key(ev):
                return (getattr(ev, 'time', None), getattr(ev, 'type', None), getattr(ev, 'player', None) or getattr(ev, 'player_out', None) or getattr(ev, 'player_in', None), getattr(ev, 'team', None))
            before_keys = {_event_key(e) for e in events}
            after_keys = {_event_key(e) for e in updated_events}
            added = after_keys - before_keys
            removed = before_keys - after_keys
            if added:
                logger.info("Reviewer added events (keys): %s", list(added))
            if removed:
                logger.info("Reviewer removed events (keys): %s", list(removed))
        except Exception:
            pass
    except Exception:
        pass
    return state
