# types.py
from typing import TypedDict, List, Optional, Any, Set
from ..models.schemas import PlayerInfo, FootballEvent


class CommentaryState(TypedDict):
    """State object for the LangGraph workflow"""
    original_commentary: str
    cleaned_commentary: str
    teams: Optional[dict]
    extracted_players: List[PlayerInfo]
    extracted_events: List[FootballEvent]
    final_analysis: Optional[dict]
    validation_issues: List[str]
    attempts: int
    predefined_teams: Optional[List[str]]
    # New fields for tracking unresolved players
    unresolved_event_players: Optional[Set[str]]
    unresolved_events: Optional[List[FootballEvent]]