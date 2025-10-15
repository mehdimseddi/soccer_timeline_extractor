# soccer_commentary_analyzer/nodes/finalize_team_codes.py
from ..state_type.types_utils import CommentaryState
from ..models.schemas import PlayerInfo
from ..config import logger

def finalize_team_codes_node(state: CommentaryState) -> CommentaryState:
    """
    Ensure every player with a resolved `team` has a corresponding `team_code` ("home" or "away").
    """
    players = state.get("extracted_players", [])
    home_team = state["teams"]["home_team"]
    away_team = state["teams"]["away_team"]

    updated_players = []
    fixed_count = 0

    for player in players:
        # Only fix if team is known but team_code is missing
        if player.team and not player.team_code:
            if player.team == home_team:
                player = player.model_copy(update={"team_code": "home"})
                fixed_count += 1
            elif player.team == away_team:
                player = player.model_copy(update={"team_code": "away"})
                fixed_count += 1
            else:
                logger.warning(f"Player {player.name} has unrecognized team: {player.team}")
        updated_players.append(player)

    logger.info(f"Finalized team_code for {fixed_count} players")
    return {**state, "extracted_players": updated_players}