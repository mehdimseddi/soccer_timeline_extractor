# models/schemas.py
"""
Pydantic models for structured output.
"""

from typing import Optional, List
from pydantic import BaseModel, Field


class FootballEvent(BaseModel):
    type: str = Field(..., enum=[
        "goal", "yellow_card", "red_card", "substitution", "penalty"
    ])
    player: Optional[str] = None
    player_out: Optional[str] = None
    player_in: Optional[str] = None
    team: Optional[str] = None
    time: str = Field(..., pattern=r"^(?:\d+|\d+\+\d+|ht|halftime|ft|fulltime)$", description="Minute, minute+stoppage, or HT/FT")
    details: str
    confidence: float = Field(ge=0.0, le=1.0)


class EventsResult(BaseModel):
    events: List[FootballEvent]


class PlayerInfo(BaseModel):
    name: str
    team: Optional[str] = None
    # team_code constrains the team to home/away in prompts; map to team at runtime
    team_code: Optional[str] = Field(
        default=None,
        description="One of 'home' or 'away' when the team is known; otherwise omitted",
        json_schema_extra={"enum": ["home", "away"]},
    )
    number: Optional[str] = None
    position: Optional[str] = Field(None, enum=[
        "goalkeeper", "right_back", "left_back", "center_back",
        "defensive_midfielder", "central_midfielder", "attacking_midfielder",
        "right_winger", "left_winger", "striker", "second_striker", "wing_back"
    ])


class LineupResult(BaseModel):
    players: List[PlayerInfo]


class TeamIdentificationResult(BaseModel):
    home_team: str
    away_team: str
    confidence: float


class MatchAnalysis(BaseModel):
    events: List[FootballEvent]
    players: Optional[List[PlayerInfo]] = None

    class Config:
        extra = 'forbid'