# utils/db_operations.py
import sqlite3
from typing import Dict, List, Optional, Any, Tuple
from contextlib import contextmanager
from .match_utils import compute_match_score
from ..config import DATABASE_PATH, logger
from ..utils.arabic import normalize_arabic_text


@contextmanager
def get_db_connection():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def get_team_name_by_id(conn: sqlite3.Connection, team_id: int) -> Optional[str]:
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM Team WHERE id = ?", (team_id,))
    row = cursor.fetchone()
    return row[0] if row else None


def list_teams(conn: sqlite3.Connection) -> list[dict]:
    """Return all teams with their ids and names."""
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM Team ORDER BY name ASC")
    rows = cursor.fetchall()
    return [{"id": r[0], "name": r[1]} for r in rows]

def get_team_id(conn: sqlite3.Connection, team_name: str) -> Optional[int]:
    """Return team ID if exists, else None."""
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM Team WHERE name = ?", (team_name,))
    row = cursor.fetchone()
    return row[0] if row else None


def get_player_id(conn: sqlite3.Connection, player_name: str) -> Optional[int]:
    """Return player ID if exists, else None."""
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM Player WHERE name = ?", (player_name,))
    row = cursor.fetchone()
    return row[0] if row else None


def get_position_code(conn: sqlite3.Connection, pos_code: str) -> Optional[str]:
    """Validate position code exists."""
    cursor = conn.cursor()
    cursor.execute("SELECT code FROM PlayerPosition WHERE code = ?", (pos_code,))
    row = cursor.fetchone()
    return row[0] if row else None


def get_event_type_code(conn: sqlite3.Connection, event_type: str) -> Optional[str]:
    """Validate event type code exists."""
    cursor = conn.cursor()
    cursor.execute("SELECT code FROM EventType WHERE code = ?", (event_type,))
    row = cursor.fetchone()
    return row[0] if row else None


# utils/db_operations.py

def insert_match(
    conn: sqlite3.Connection,
    home_team_name: str,
    away_team_name: str,
    match_date: str,
    home_score: Optional[int] = None,
    away_score: Optional[int] = None
) -> Optional[int]:
    """Insert match only if both teams exist. Scores are optional."""
    home_team_id = get_team_id(conn, home_team_name)
    away_team_id = get_team_id(conn, away_team_name)

    if not home_team_id:
        logger.error(f"Unknown home team: {home_team_name}")
        return None
    if not away_team_id:
        logger.error(f"Unknown away team: {away_team_name}")
        return None

    # Default scores to 0 if not provided
    h_score = home_score if home_score is not None else 0
    a_score = away_score if away_score is not None else 0

    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO Match (
            home_team_id, away_team_id, match_date, home_score, away_score
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (home_team_id, away_team_id, match_date, h_score, a_score)
    )
    match_id = cursor.lastrowid
    logger.info(f"Match created: ID {match_id} → {home_team_name} {h_score} - {a_score} {away_team_name}")
    return match_id

def insert_match_lineup(
    conn: sqlite3.Connection,
    match_id: int,
    player_name: str,
    team_name: str,           # <-- NEW: team in this match
    jersey_number: Optional[str],
    position_code: Optional[str]
):
    """Insert lineup only if player and team exist, and link team played for."""
    player_id = get_player_id(conn, player_name)
    if not player_id:
        logger.warning(f"Skipping lineup: Unknown player '{player_name}'")
        return False

    team_id = get_team_id(conn, team_name)
    if not team_id:
        logger.warning(f"Skipping lineup: Player '{player_name}' - unknown team '{team_name}'")
        return False

    if position_code:
        valid_pos = get_position_code(conn, position_code)
        if not valid_pos:
            logger.warning(f"Invalid position code '{position_code}' for player '{player_name}'")
            return False

    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO MatchLineup (match_id, player_id, team_id, jersey_number, position_code)
            VALUES (?, ?, ?, ?, ?)
            """,
            (match_id, player_id, team_id, jersey_number, position_code)
        )
        logger.info(f"Lineup: {player_name} ({team_name}) #{jersey_number or ''} ({position_code or 'N/A'})")
        return True
    except sqlite3.IntegrityError as e:
        if "UNIQUE" in str(e):
            logger.error(f"Duplicate lineup entry: {player_name} already in match {match_id}")
        else:
            logger.error(f"DB Error inserting lineup: {e}")
        return False

def insert_match_event(
    conn: sqlite3.Connection,
    match_id: int,
    event: Dict[str, Any]
):
    """Insert event only if all referenced entities exist."""
    event_type = event["type"]
    valid_type = get_event_type_code(conn, event_type)
    if not valid_type:
        logger.warning(f"Skipping event: Unknown event type '{event_type}'")
        return False

    player_id = None
    if event.get("player"):
        player_id = get_player_id(conn, event["player"])
        if not player_id:
            logger.warning(f"Skipping event: Unknown player '{event['player']}'")
            return False

    player_in_id = None
    if event.get("player_in"):
        player_in_id = get_player_id(conn, event["player_in"])
        if not player_in_id:
            logger.warning(f"Skipping substitution: Unknown incoming player '{event['player_in']}'")
            return False

    player_out_id = None
    if event.get("player_out"):
        player_out_id = get_player_id(conn, event["player_out"])
        if not player_out_id:
            logger.warning(f"Skipping substitution: Unknown outgoing player '{event['player_out']}'")
            return False

    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO MatchEvent (
            match_id, player_id, event_type_code, time, details, player_in_id, player_out_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            match_id,
            player_id,
            event_type,
            event["time"],
            event["details"],
            player_in_id,
            player_out_id
        )
    )
    logger.info(f"Event: [{event['time']}] {event_type} by {event.get('player', 'N/A')}")
    return True

def save_analysis_to_database(
    home_team_name: str,
    away_team_name: str,
    match_date: str,
    events: List[Dict],
    players: List[Dict]
):
    # Compute score
    score = compute_match_score(events, home_team=home_team_name, away_team=away_team_name)
    home_score = score.get(home_team_name, 0)
    away_score = score.get(away_team_name, 0)

    with get_db_connection() as conn:
        # 1. Insert match (fails if teams don't exist)
        match_id = insert_match(
            conn,
            home_team_name=home_team_name,
            away_team_name=away_team_name,
            match_date=match_date,
            home_score=home_score,
            away_score=away_score
        )
        if not match_id:
            logger.error("Aborting: Could not create match due to invalid teams.")
            return None

        # 2. Insert lineups (deduplicate and skip unknowns preemptively)
        def _key_for_player(name: Optional[str], team: Optional[str]) -> Tuple[str, str]:
            safe_name = normalize_arabic_text(name or "").strip()
            safe_team = (team or "").strip()
            return (safe_name, safe_team)

        seen_pairs: set[Tuple[str, str]] = set()
        total_input_players = len(players)
        lineup_count = 0
        skipped_unknown = 0
        skipped_duplicates = 0

        for player_data in players:
            # Extract attributes safely from pydantic model-like objects
            p_name = getattr(player_data, 'name', None)
            p_team = getattr(player_data, 'team', None)
            p_number = getattr(player_data, 'number', None)
            p_position = getattr(player_data, 'position', None)

            # Require both name and team for lineup persistence
            if not p_name or not p_team:
                skipped_unknown += 1
                continue

            # Deduplicate by normalized (name, team)
            k = _key_for_player(p_name, p_team)
            if k in seen_pairs:
                skipped_duplicates += 1
                continue

            # Validate existence in DB before attempting insert
            if get_player_id(conn, p_name) is None:
                skipped_unknown += 1
                continue
            if get_team_id(conn, p_team) is None:
                skipped_unknown += 1
                continue

            # Passed all checks: remember and insert
            seen_pairs.add(k)
            success = insert_match_lineup(
                conn=conn,
                match_id=match_id,
                player_name=p_name,
                team_name=p_team,
                jersey_number=p_number,
                position_code=p_position
            )
            if success:
                lineup_count += 1

        logger.info(
            f"Added {lineup_count}/{total_input_players} players to lineup"
            + (f" (skipped {skipped_duplicates} duplicates, {skipped_unknown} unknowns)" if (skipped_duplicates or skipped_unknown) else "")
        )

        # 3. Insert events
        event_count = 0
        for event in events:
            event_dict = {
                "type": event.type,
                "time": event.time,
                "player": event.player,
                "team": event.team,
                "details": event.details,
                "player_in": getattr(event, "player_in", None),
                "player_out": getattr(event, "player_out", None)
            }
            if insert_match_event(conn, match_id, event_dict):
                event_count += 1

        logger.info(f"Added {event_count}/{len(events)} events to match ID {match_id}")
        return match_id  # return match ID for logging or further use
