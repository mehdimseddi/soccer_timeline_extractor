import os
import pandas as pd
from typing import Any, List, Dict
from pathlib import Path
import csv
from ..config import OUTPUT_DIR, logger  # This should be a directory path, not a file
import uuid


def save_analysis_to_excel(
    analysis_results: List[Dict[str, Any]]
) -> str:
    """
    Save match analysis results to an Excel file with formatting.
    
    Args:
        analysis_results: List of analysis dictionaries containing match_info, events, players.
    
    Returns:
        Path to the created Excel file
    """
    import uuid

    # Collect all events and players into flat lists
    all_events = []
    all_players = []
    
    match_info = analysis_results.get('match_info', {})
    match_id = match_info.get('match_id', str(uuid.uuid4()))
    home_team = match_info.get('home_team', 'Unknown')
    away_team = match_info.get('away_team', 'Unknown')
    match_date = match_info.get('date', 'Unknown')
    
    # Events
    for event in analysis_results.get('events', []):
        all_events.append({
            "match_id": match_id,
            "home_team": home_team,
            "away_team": away_team,
            "match_date": match_date,
            "event_type": event.type.replace('_', ' '),
            "event_time": event.time,
            "player": event.player if event.player else "",
            "player_out": event.player_out if event.player_out else "",
            "player_in": event.player_in if event.player_in else "",
            "team": event.team if event.team else "",
            "details": event.details if event.details else "",
            "confidence": event.confidence if event.confidence else 0.0
        })
    
    # Players
    for player in analysis_results.get('players', []):
        all_players.append({
            "match_id": match_id,
            "home_team": home_team,
            "away_team": away_team,
            # "match_date": match_date,
            "name": player.name if player.name else "",
            "team": player.team if player.team else "",
            "number": player.number if player.number else "",
            "position": player.position if player.position else "",
        })
    
    # Create DataFrames
    events_df = pd.DataFrame(all_events)
    players_df = pd.DataFrame(all_players)
    

    # Prepare output paths
    output_dir = Path(os.path.join(OUTPUT_DIR, match_id))
    output_dir.mkdir(parents=True, exist_ok=True)

    excel_path = output_dir / "match.xlsx"

    # Write to Excel with formatting
    with pd.ExcelWriter(excel_path, engine='xlsxwriter') as writer:
        events_df.to_excel(writer, sheet_name='Events', index=False)
        players_df.to_excel(writer, sheet_name='Players', index=False)

        workbook = writer.book
        events_sheet = writer.sheets['Events']
        players_sheet = writer.sheets['Players']

        # Define a format with color
        header_format = workbook.add_format({
            'bold': True,
            'bg_color': '#B0C4DE',  # Light Steel Blue
            'border': 1
        })

        # Apply header format
        for col_num, value in enumerate(events_df.columns.values):
            events_sheet.write(0, col_num, value, header_format)
        
        for col_num, value in enumerate(players_df.columns.values):
            players_sheet.write(0, col_num, value, header_format)

        # Optional: Autofit columns
        for sheet, df in zip([events_sheet, players_sheet], [events_df, players_df]):
            for i, col in enumerate(df.columns):
                max_width = max(df[col].astype(str).map(len).max(), len(col)) + 2
                sheet.set_column(i, i, max_width)

    logger.info(f"Excel report saved: {excel_path}")
    return str(excel_path)

def save_analysis_to_csv(
    analysis_results: List[Dict[str, Any]]
) -> Any:
    """
    Save match analysis results to two CSV files: one for events, one for players.
    
    Args:
        analysis_results: List of analysis result dictionaries containing match_info, events, and players.
    
    Returns:
        Dictionary with paths to saved CSV files.
    """

    all_events = []
    all_players = []

    match_info = analysis_results.get('match_info', {})
    home_team = match_info.get('home_team', 'Unknown')
    away_team = match_info.get('away_team', 'Unknown')
    match_date = match_info.get('date', 'Unknown')
    match_id = match_info.get('match_id', str(uuid.uuid4()))

    for event in analysis_results.get('events', []):
        all_events.append({
            "match_id": match_id,
            "home_team": home_team,
            "away_team": away_team,
            "match_date": match_date,
            "event_type": event.type.replace('_', ' '),
            "event_time": event.time,
            "player": event.player or "",
            "player_out": getattr(event, "player_out", ""),
            "player_in": getattr(event, "player_in", ""),
            "team": event.team or "",
            "details": event.details or "",
            "confidence": event.confidence or 0.0
        })

    for player in analysis_results.get('players', []):
        all_players.append({
            "match_id": match_id,
            "home_team": home_team,
            "away_team": away_team,
            "name": player.name or "",
            "team": player.team or "",
            "number": player.number or "",
            "position": player.position or ""
        })
    # Prepare output paths
    output_dir = Path(os.path.join(OUTPUT_DIR, match_id))
    output_dir.mkdir(parents=True, exist_ok=True)

    events_csv_path = output_dir / "events.csv"
    players_csv_path = output_dir / "players.csv"

    # Define headers
    event_headers = list(all_events[0].keys()) if all_events else []
    player_headers = list(all_players[0].keys()) if all_players else []

    # Write events CSV
    if all_events:
        with open(events_csv_path, mode='w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=event_headers)
            writer.writeheader()
            writer.writerows(all_events)

    # Write players CSV
    if all_players:
        with open(players_csv_path, mode='w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=player_headers)
            writer.writeheader()
            writer.writerows(all_players)

    logger.info(f"CSV saved: events={events_csv_path}, players={players_csv_path}")
    return str(events_csv_path), str(players_csv_path)
    
