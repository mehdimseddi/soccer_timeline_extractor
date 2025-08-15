# main.py
from datetime import datetime
from typing import Any, Dict, List, Tuple, Optional
import argparse
import os
import sys
import uuid

from .graph.workflow import build_soccer_analysis_graph
from .models.schemas import MatchAnalysis
from .utils.arabic import display_arabic
from .config import (DATABASE_PATH, COMMENTARY_PATH, logger)
from .utils.db_utils import get_all_team_names
from .utils.visualization import save_analysis_to_excel, save_analysis_to_csv
from .utils.match_utils import compute_match_score
from .utils.db_operations import (
    get_db_connection,
    insert_match,
    insert_match_lineup,
    insert_match_event
)
from .utils.db_setup import setup_enum_tables  # call once
from .utils.youtube import download_youtube_audio_to_wav, YouTubeDownloadError
from .utils.audio_transcription import transcribe_audio_file


def analyze_soccer_commentary(commentary: str, home_team: str = None, away_team: str = None, predefined_teams: List[str] = None) -> Any:
    graph = build_soccer_analysis_graph()
    initial_state = {
        "original_commentary": commentary,
        "teams": {"home_team": home_team, "away_team": away_team, "all_teams": [home_team, away_team], "confidence": 1.0} if home_team and away_team else None,
        "validation_issues": [],
        "attempts": 0,
        "predefined_teams": predefined_teams if predefined_teams else None,
    }
    final_state = graph.invoke(initial_state)
    return MatchAnalysis(**final_state["final_analysis"]), final_state["teams"]["home_team"], final_state["teams"]["away_team"]


# ======================
# INTERACTIVE SELECTION
# ======================

def select_teams_interactively() -> Tuple[Optional[str], Optional[str], Optional[List[str]]]:
    """
    Displays all teams from database and lets user select home and away teams.
    Returns tuple of (home_team, away_team, all_teams) or (None, None, teams) if selection is skipped.
    """
    teams = get_all_team_names(DATABASE_PATH)
    if not teams:
        logger.error("No teams found in database!")
        print("No teams found in database!")
        return None, None, None

    print("\nAvailable Teams:")
    for idx, team in enumerate(teams, start=1):
        print(f"{idx}. {display_arabic(team)}")

    def get_team_selection(prompt: str) -> Optional[str]:
        while True:
            try:
                selection = input(prompt)
                if selection.lower() == 'q':
                    return None
                team_idx = int(selection) - 1
                if 0 <= team_idx < len(teams):
                    return teams[team_idx]
                print(f"Please enter a number between 1 and {len(teams)}")
            except ValueError:
                print("Please enter a valid number or 'q' to quit")

    print("\nSelect HOME team:")
    home_team = get_team_selection("Enter number (or 'q' to skip): ")
    if not home_team:
        return None, None, teams

    print("\nSelect AWAY team (must be different from home team):")
    while True:
        away_team = get_team_selection("Enter number (or 'q' to skip): ")
        if not away_team:
            return None, None, teams
        if away_team != home_team:
            break
        print("Away team must be different from home team!")

    return home_team, away_team, teams


# ======================
# CLI ENTRYPOINT
# ======================

def run_diagnostics() -> int:
    """Run readiness checks for CLI and environment (no LLM calls)."""
    from pathlib import Path
    errors: List[str] = []

    # DB presence and teams
    if not os.path.exists(DATABASE_PATH):
        errors.append(f"Database not found at {DATABASE_PATH}")
    else:
        try:
            teams = get_all_team_names(DATABASE_PATH)
            if not teams:
                errors.append("No teams found in database. Initialize DB first.")
            else:
                logger.info(f"Teams available: {len(teams)}")
        except Exception as e:
            errors.append(f"Failed to query teams: {e}")

    # Commentary file presence
    if not os.path.exists(COMMENTARY_PATH):
        errors.append(f"Commentary file missing at {COMMENTARY_PATH}")

    # Graph build
    try:
        build_soccer_analysis_graph()
        logger.info("Graph compiled successfully")
    except Exception as e:
        errors.append(f"Graph build failed: {e}")

    # Output directory writability
    try:
        test_path = Path(os.path.join(os.path.dirname(COMMENTARY_PATH), 'output', 'diagnostics.tmp'))
        test_path.parent.mkdir(parents=True, exist_ok=True)
        test_path.write_text("ok", encoding="utf-8")
        test_path.unlink(missing_ok=True)
        logger.info("Output directory is writable")
    except Exception as e:
        errors.append(f"Output directory not writable: {e}")

    if errors:
        for msg in errors:
            logger.error(msg)
            print(f"❌ {msg}")
        return 1
    try:
        print("✅ Diagnostics passed. Ready for analysis.")
    except Exception:
        print("Diagnostics passed. Ready for analysis.")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Soccer commentary analyzer (CLI)")
    parser.add_argument("--diagnostics", action="store_true", help="Run readiness checks and exit")
    parser.add_argument("--youtube-url", type=str, default=None, help="Download audio from a YouTube URL and analyze it")
    args = parser.parse_args(argv)

    if args.diagnostics:
        return run_diagnostics()

    setup_enum_tables()  # idempotent

    # Ingest source: either YouTube URL or local file
    if args.youtube_url:
        print("Fetching audio from YouTube…")
        try:
            dl = download_youtube_audio_to_wav(args.youtube_url)
        except YouTubeDownloadError as e:
            logger.error(f"YouTube download failed: {e}")
            print(f"❌ YouTube download failed: {e}")
            return 1
        try:
            commentary = transcribe_audio_file(dl.wav_path)
        finally:
            dl.cleanup()
        if not commentary:
            print("❌ Transcription produced no text.")
            return 1
    else:
        # Read commentary from file
        try:
            with open(COMMENTARY_PATH, "r", encoding="utf-8") as file:
                commentary = file.read()
        except FileNotFoundError:
            logger.error("Could not find commentary.txt! Please make sure the file exists.")
            print("❌ Could not find commentary.txt! Please make sure the file exists.")
            return 1

    # Team selection
    try:
        print(display_arabic("🏆 نظام اختيار الفريق"))
    except Exception:
        print("Team selection system")
    home_team, away_team, teams = select_teams_interactively()

    if home_team and away_team:
        print(f"\nSelected teams: {display_arabic(home_team)} (Home) vs {display_arabic(away_team)} (Away)")
    else:
        print("Proceeding without team selection")

    logger.info("Starting commentary analysis with LangGraph...")
    try:
        print(display_arabic("Starting commentary analysis with LangGraph..."))
    except Exception:
        print("Starting commentary analysis with LangGraph...")
    print(f"Commentary length: {len(commentary)} characters")

    try:
        result, home_team, away_team = analyze_soccer_commentary(
            commentary, home_team=home_team, away_team=away_team, predefined_teams=teams
        )
    except Exception as e:
        logger.error(f"CLI analysis failed: {e}", exc_info=True)
        print("❌ Analysis failed. See logs for details.")
        return 1

    score = compute_match_score(result.events, home_team=home_team, away_team=away_team)

    # Output summary
    print(display_arabic("="*50))
    if score:
        try:
            print("\n" + display_arabic("📊 نتيجة المباراة:"))
            print(display_arabic(f"  {home_team} {score[home_team]} - {score[away_team]} {away_team}"))
        except Exception:
            print("Match result:")
            print(f"  {home_team} {score[home_team]} - {score[away_team]} {away_team}")
    else:
        try:
            print(display_arabic("❌ لم يتم تسجيل أي هدف في المباراة."))
        except Exception:
            print("No goals were recorded.")

    print("\n" + display_arabic("="*50))
    try:
        print(display_arabic("🎯 الأحداث المستخرجة:"))
    except Exception:
        print("Extracted events:")
    print(display_arabic("="*50))

    for i, event in enumerate(result.events, 1):
        time_display = event.time
        type_display = event.type.replace('_', ' ')
        if event.type == "substitution":
            player_display = f"Out: {event.player_out if event.player_out else 'N/A'}, In: {event.player_in if event.player_in else 'N/A'}"
        else:
            player_display = event.player if event.player else "N/A"
        team_display = event.team if event.team else "N/A"
        details_display = event.details

        try:
            print(f"\n{display_arabic(f'{i}. [{time_display}] {type_display}')}" ) 
            print(display_arabic(f"   👤 اللاعب: {player_display}"))
            print(display_arabic(f"   🛡️  الفريق: {team_display}"))
            print(display_arabic(f"   📝 الوصف: {details_display}"))
        except Exception:
            print(f"\n{i}. [{time_display}] {type_display}")
            print(f"   player: {player_display}")
            print(f"   team: {team_display}")
            print(f"   details: {details_display}")
        print(display_arabic(f"   💯 الثقة: {event.confidence:.2f}"))

    print("\n" + display_arabic("="*50))
    try:
        print(display_arabic("👥 المعلومات عن اللاعبين:"))
    except Exception:
        print("Players:")
    print(display_arabic("="*50))

    for i, player in enumerate(result.players, 1):
        try:
            print(display_arabic(f"\n{i}. {player.name}"))
            print(display_arabic(f"   🛡️  الفريق: {player.team if player.team else 'N/A'}"))
            print(display_arabic(f"   #️⃣ الرقم: {player.number if player.number else 'N/A'}"))
            print(display_arabic(f"   📍 المركز: {player.position if player.position else 'N/A'}"))
        except Exception:
            print(f"\n{i}. {player.name}")
            print(f"   team: {player.team if player.team else 'N/A'}")
            print(f"   number: {player.number if player.number else 'N/A'}")
            print(f"   position: {player.position if player.position else 'N/A'}")

    # Save artifacts
    analysis_results = {
        'match_info': {
            'match_id': str(uuid.uuid4()),
            'home_team': home_team,
            'away_team': away_team,
            'date': datetime.now().strftime("%Y-%m-%d")
        },
        'events': result.events,
        'players': result.players
    }

    xlsx_path = save_analysis_to_excel(analysis_results)
    events_csv_path, players_csv_path = save_analysis_to_csv(analysis_results)
    print("\n" + display_arabic("="*50))
    print(f"\nAnalysis saved to xlsx: {xlsx_path}")
    print(f"Events CSV saved to: {events_csv_path}")
    print(f"Players CSV saved to: {players_csv_path}")
    print(display_arabic("="*50))
    logger.info("CLI analysis completed successfully")
    return 0


if __name__ == "__main__":
    sys.exit(main())
