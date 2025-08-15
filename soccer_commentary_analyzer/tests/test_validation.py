import pytest
from soccer_commentary_analyzer.nodes.validation import validate_analysis_node
from soccer_commentary_analyzer.state_type.types_utils import CommentaryState
from soccer_commentary_analyzer.models.schemas import FootballEvent, PlayerInfo


def base_state(**overrides):
    state: CommentaryState = {
        "original_commentary": "",
        "cleaned_commentary": "",
        "teams": {"home_team": "الترجي", "away_team": "الصفاقسي", "all_teams": ["الترجي", "الصفاقسي"], "confidence": 1.0},
        "extracted_players": [],
        "extracted_events": [],
        "final_analysis": None,
        "validation_issues": [],
        "attempts": 0,
        "predefined_teams": None,
    }
    state.update(overrides)
    return state


def test_validation_flags_empty_events():
    state = base_state()
    out = validate_analysis_node(state)
    assert any("No match events were extracted" in i for i in out["validation_issues"]) 


def test_validation_checks_substitution_integrity():
    events = [
        FootballEvent(type="substitution", time="60", details="", confidence=0.9, player_out=None, player_in="X"),
        FootballEvent(type="substitution", time="70", details="", confidence=0.9, player_out="Y", player_in=None),
    ]
    state = base_state(extracted_events=events)
    out = validate_analysis_node(state)
    assert any("missing player_in/player_out" in i for i in out["validation_issues"])


def test_validation_requires_player_or_team_non_sub():
    events = [
        FootballEvent(type="goal", time="23", details="", confidence=0.9, player=None, team=None)
    ]
    state = base_state(extracted_events=events)
    out = validate_analysis_node(state)
    assert any("neither player nor team" in i for i in out["validation_issues"]) 
