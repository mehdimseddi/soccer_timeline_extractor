# utils/match_utils.py
from typing import List, Dict
from ..models.schemas import FootballEvent  # Adjust import as needed

def compute_match_score(events: List[FootballEvent], home_team: str, away_team: str) -> Dict[str, int]:
    """
    Compute the final match score from goal events.
    Returns dict: {home_team: goals, away_team: goals}
    """
    score = {home_team: 0, away_team: 0}
    for event in events:
        if getattr(event, "type", "") == "goal" and event.team:
            team = event.team.strip()
            if team in score:
                score[team] += 1
    return score