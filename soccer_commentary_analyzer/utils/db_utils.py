
import sqlite3
from typing import List
from .arabic import normalize_arabic_text
from rapidfuzz import process, fuzz
from ..config import DATABASE_PATH


def get_all_team_names(db_path: str) -> List[str]:
    """Fetch all team names from the database."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT name FROM TEAM")
    teams = [row[0] for row in cursor.fetchall()]
    conn.close()
    return teams


def get_all_player_names(db_path: str = DATABASE_PATH) -> List[str]:
    """Fetch all canonical player names."""
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("SELECT name FROM PLAYER")
    names = [row[0] for row in c.fetchall()]
    conn.close()
    return names


def get_canonical_player_name(name: str, db_path: str = DATABASE_PATH) -> str:
    """Return canonical name if exact match exists."""
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("SELECT name FROM PLAYER WHERE name = ?", (name,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else None


def find_best_player_match(
    transcript_name: str,
    player_names_for_search: list,
    threshold: int = 85,
    team_hint: str = None,
    db_path: str = DATABASE_PATH
) -> tuple:
    """
    Fuzzy match a player name from transcript to canonical names with enhanced context.
    """
    if not player_names_for_search or not transcript_name.strip():
        return None, 0

    norm_transcript = normalize_arabic_text(transcript_name)

    norm_player_list = [normalize_arabic_text(name) for name in player_names_for_search]

    norm_to_orig = {
        norm_player_list[i]: player_names_for_search[i]
        for i in range(len(player_names_for_search))
    }

    player_metadata = {}
    if db_path:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT p.name, t.name
            FROM PLAYER p
            LEFT JOIN PlayerTeam pt ON p.id = pt.player_id
            LEFT JOIN TEAM t ON pt.team_id = t.id
        """)
        for row in cursor.fetchall():
            p_name, team_name = row
            if p_name not in player_metadata:
                player_metadata[p_name] = {"teams": []}
            if team_name:
                player_metadata[p_name]["teams"].append(team_name)
        conn.close()

    def scorer_with_context(query_norm, candidate_norm):
        base_score = fuzz.WRatio(query_norm, candidate_norm)
        orig_candidate = norm_to_orig.get(candidate_norm)
        if not orig_candidate:
            return base_score

        meta = player_metadata.get(orig_candidate, {})
        if team_hint and team_hint in meta.get("teams", []):
            base_score += 10
            base_score = min(base_score, 100.0)

        return base_score

    scored_matches = []
    for norm_name in norm_player_list:
        score = scorer_with_context(norm_transcript, norm_name)
        if score >= threshold:
            scored_matches.append((norm_name, score))

    if not scored_matches:
        return None, 0

    best_norm, best_score = max(scored_matches, key=lambda x: x[1])

    return norm_to_orig[best_norm], best_score


def get_possible_teams_for_player(player_name: str, db_path: str = DATABASE_PATH) -> List[str]:
    """Get all teams associated with a player."""
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("""
        SELECT t.name FROM TEAM t
        JOIN PlayerTeam pt ON t.id = pt.team_id
        JOIN PLAYER p ON p.id = pt.player_id
        WHERE p.name = ?
    """, (player_name,))
    results = c.fetchall()
    conn.close()
    return [row[0] for row in results]


def validate_llm_team_names(llm_teams: List[str], home_team: str = None, away_team: str = None, db_path: str = DATABASE_PATH) -> dict:
    """Validate and correct LLM-extracted team names against DB."""
    from .arabic import normalize_arabic_text
    from rapidfuzz import process, fuzz

    db_team_names = get_all_team_names(db_path)
    norm_db_teams = {normalize_arabic_text(name): name for name in db_team_names}

    def validate_single(team_name):
        if not team_name:
            return None
        norm = normalize_arabic_text(team_name)
        if norm in norm_db_teams:
            return norm_db_teams[norm]
        match = process.extractOne(norm, norm_db_teams.keys(), scorer=fuzz.WRatio, score_cutoff=85)
        return norm_db_teams[match[0]] if match else team_name

    validated = [validate_single(t) for t in llm_teams if validate_single(t)]
    return {
        "home_team": validate_single(home_team) or (validated[0] if validated else None),
        "away_team": validate_single(away_team) or (validated[1] if len(validated) > 1 else None),
        "all_teams": validated
    }
