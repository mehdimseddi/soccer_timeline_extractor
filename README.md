# Soccer Commentary Analyzer

**Soccer Commentary Analyzer** is a Python application that extracts structured match data (goals, cards, substitutions, players) from Arabic soccer commentary text using advanced Large Language Models (LLMs). It can also transcribe YouTube videos or audio files and then analyze the resulting text.

## Features

*   **Multi-Stage Analysis:** Employs a graph-based workflow (`LangGraph`) to iteratively refine player and event extraction.
*   **LLM Powered:** Leverages Google's `gemini-2.5-flash-lite` and `gemini-2.5-pro` models for understanding commentary.
*   **Database Integration:** Uses a local SQLite database for player/team canonical names.
*   **Data Exports:** Outputs results to Excel and CSV formats.
*   **CLI & API:** Offers both a command-line interface and a FastAPI web server.
*   **Audio Transcription:** Uses google SpeechRecognition for transcribing audio/video files.
*   **YouTube Support:** Fetch and analyze commentary directly from YouTube URLs.

## Table of Contents

1.  [Prerequisites](#prerequisites)
2.  [Installation](#installation)
3.  [Environment Variables](#environment-variables)
4.  [Project Structure](#project-structure)
5.  [Database](#database)
6.  [Preparing Your Input](#preparing-your-input)
7.  [Using the CLI](#using-the-cli)
8.  [Using the API Server](#using-the-api-server)
9.  [Development Notes](#development-notes)

## Prerequisites

Before you begin, ensure you have met the following requirements:

*   **Python:** Python 3.10 or newer.
*   **Git:** For cloning the repository (recommended).
*   **FFmpeg:** Required for audio processing (YouTube/audio transcription).
    *   **Linux (Ubuntu/Debian):** `sudo apt update && sudo apt install ffmpeg`
    *   **macOS (Homebrew):** `brew install ffmpeg`
    *   **Windows:** Download from [https://www.gyan.dev/ffmpeg/builds/](https://www.gyan.dev/ffmpeg/builds/) and add to your `PATH`.
*   **Google API Key:** A valid Google API key with access to Generative AI (Gemini) models.
*   **Virtual Environment (Recommended):** Isolate project dependencies.

## Installation

1.  **Clone the Repository:**

    ```bash
    git clone https://github.com/C00LiMoUn/soccer_commentary_analyzer.git
    cd soccer_commentary_analyzer
    ```

2.  **Create a Virtual Environment (Recommended):**

    Creating a virtual environment keeps your project dependencies separate from your system's Python packages.

    **Linux/macOS:**
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```

    **Windows:**
    ```cmd
    python -m venv venv
    venv\Scripts\activate.bat
    # Or for PowerShell: venv\Scripts\Activate.ps1
    ```

3.  **Install Dependencies:**

    Install the required Python packages using `pip` and the provided `requirements.txt` file.

    ```bash
    pip install -r requirements.txt
    ```
## Environment Variables

The application uses environment variables for configuration. Copy the example file and modify it as needed.

1.  **Copy the example file:**

    ```bash
    cp .env.example .env
    ```

2.  **Edit `.env`:**

    Open the `.env` file in a text editor and fill in the required values:

    ```
    GOOGLE_API_KEY=your_actual_google_api_key_here
    ```

    *   **`GOOGLE_API_KEY`:** (**REQUIRED**) Replace `your_actual_google_api_key_here` with your valid Google API key.
    *   Other variables control various aspects of the analysis logic (e.g., how strictly to enforce rosters, confidence thresholds). Refer to `config.py` for details if you need to tweak them.

## Project Structure

Understanding the layout helps navigate the codebase.

```
soccer_commentary_analyzer/
├── README.md                   # This file
├── requirements.txt            # Python package dependencies
├── config.py                   # Configuration loader, LLM factory, constants
├── main.py                     # Main CLI entrypoint
├── app.py                      # FastAPI backend application
├── commentary.txt              # Default input file for CLI/API text analysis
├── .env.example                # Template for environment variables
├── .env                        # (YOU CREATE THIS) Your local environment variables
├── .gitignore                  # Files/dirs ignored by Git
│
├── database/                   # Database files
│   └── teams_players.db       # SQLite database with team/player names (populated by scripts)
│
├── output/                     # Directory where analysis results (Excel, CSV) are saved
│
├── temp/                      # Temporary files (e.g., for audio processing)
│
├── graph/                      # Defines the LangGraph workflow
│   └── workflow.py
│
├── nodes/                      # Individual processing steps of the workflow (LangGraph nodes)
│   ├── cleaning.py
│   ├── team_identification.py
│   ├── player_extraction.py
│   ├── processing.py (event extraction)
│   ├── composition.py
│   ├── validation.py
│   ├── reviewer.py
│   ├── compile.py
│   └── ... (others)
│
├── models/                     # Pydantic schemas defining structured output
│   ├── schemas.py
│   └── ...
│
├── prompts/                    # LLM prompts for different tasks
│   ├── team_identification.py
│   ├── lineup.py (player extraction)
│   ├── events.py (event extraction)
│   ├── reviewer.py
│   └── ...
│
├── utils/                      # Utility functions
│   ├── db_utils.py             # Database interaction (lookup, validation)
│   ├── arabic.py               # Arabic text normalization/display
│   ├── audio_transcription.py  # Audio transcription logic (Whisper)
│   ├── youtube.py              # YouTube download logic
│   ├── visualization.py        # Saving to Excel/CSV
│   └── ...
│
├── tests/                      # Unit/integration tests
│   └── ...
│
└── other/                      # Helper scripts (database init, logo fetching)
    ├── init_database_with_scraping.py
    ├── fetch_team_logos.py
    └── ...
```

## Database

This application uses a local **SQLite database** (`database/teams_players.db`) for two main purposes:

1.  **Reference Data:** Storing canonical information about known teams and players (like a knowledge base).
2.  **Operational Data:** Storing the results (matches, lineups, events) of analyses performed by the application.

#### Database Schema Explanation

The structure of the database consists of tables for reference data and tables for storing analysis results.

**1. Reference Data Tables (Static/Slow-changing)**

These tables hold the foundational data used for validation and normalization.

*   **`TEAM`**:
    *   **Purpose:** Stores unique identifiers and names for soccer teams.
    *   **Columns:**
        *   `id` (INTEGER, Primary Key): A unique numerical identifier for each team.
        *   `name` (TEXT, Unique): The canonical full name of the team (e.g., "الترجي الرياضي التونسي", "النادي الرياضي البنزرتي").

*   **`PLAYER`**:
    *   **Purpose:** Stores unique identifiers and canonical full names for soccer players.
    *   **Columns:**
        *   `id` (INTEGER, Primary Key): A unique numerical identifier for each player.
        *   `name` (TEXT, Unique): The canonical full name of the player (e.g., "زياد العونلي", "محمد بن علي").

*   **`PlayerTeam`**:
    *   **Purpose:** A junction/bridge table that defines the many-to-many relationship between players and teams. It represents historical or current roster affiliations.
    *   **Columns:**
        *   `id` (INTEGER, Primary Key): A unique identifier for each player-team link.
        *   `player_id` (INTEGER, Foreign Key): References the `id` column in the `PLAYER` table.
        *   `team_id` (INTEGER, Foreign Key): References the `id` column in the `TEAM` table.
    *   **Example:** Links "زياد العونلي" to "النادي الرياضي البنزرتي".

*   **Enumeration Tables:**
    *   Store predefined lists of valid values for consistency in analysis results.
    *   **`EventType`**:
        *   **Purpose:** Defines valid match event types.
        *   **Columns:**
            *   `code` (TEXT, Primary Key): Event type code (e.g., "goal", "yellow_card").
            *   `description` (TEXT, Not Null): Description.
    *   **`PlayerPosition`**:
        *   **Purpose:** Defines standard playing positions.
        *   **Columns:**
            *   `code` (TEXT, Primary Key): Position code (e.g., "goalkeeper", "striker").
            *   `description` (TEXT, Not Null): Description.

**2. Operational Data Tables (Dynamic/Populated by Analysis)**

These tables are filled as the application analyzes commentary and saves the structured results.

*   **`Match`**:
    *   **Purpose:** Represents a single soccer match that has been analyzed.
    *   **Columns:**
        *   `id` (INTEGER, Primary Key): Unique identifier for the match.
        *   `home_team_id` (INTEGER, Foreign Key): References the `id` of the home team in the `TEAM` table.
        *   `away_team_id` (INTEGER, Foreign Key): References the `id` of the away team in the `TEAM` table.
        *   `home_score` (INTEGER, Default 0): Final score for the home team.
        *   `away_score` (INTEGER, Default 0): Final score for the away team.
        *   `match_date` (DATETIME, Not Null): Date and time the match took place (often set to analysis time if actual date unknown).

*   **`MatchLineup`**:
    *   **Purpose:** Stores the players who participated (started or were substitutes) in a specific `Match`, along with their team affiliation for that match and optional details like jersey number/position.
    *   **Columns:**
        *   `id` (INTEGER, Primary Key): Unique identifier for the lineup entry.
        *   `match_id` (INTEGER, Foreign Key): References the `id` of the match in the `Match` table.
        *   `player_id` (INTEGER, Foreign Key): References the `id` of the player in the `PLAYER` table.
        *   `team_id` (INTEGER, Foreign Key): References the `id` of the team the player played for *in this specific match* (should align with `Match.home_team_id` or `Match.away_team_id`).
        *   `jersey_number` (TEXT): The player's jersey number for this match (if known).
        *   `position_code` (TEXT, Foreign Key): References the `code` in the `PlayerPosition` table (e.g., "goalkeeper").

*   **`MatchEvent`**:
    *   **Purpose:** Records a specific event (goal, card, substitution, etc.) that occurred during a `Match`.
    *   **Columns:**
        *   `id` (INTEGER, Primary Key): Unique identifier for the event.
        *   `match_id` (INTEGER, Foreign Key): References the `id` of the match in the `Match` table.
        *   `player_id` (INTEGER, Foreign Key, Nullable): References the `id` of the main player involved in the event (e.g., player who scored a goal). `NULL` for events not tied to a specific player.
        *   `event_type_code` (TEXT, Foreign Key): References the `code` in the `EventType` table (e.g., "goal", "yellow_card").
        *   `time` (TEXT, Not Null): The minute (or time format like "45+2") when the event occurred.
        *   `details` (TEXT): A short description or additional context for the event.
        *   `player_in_id` (INTEGER, Foreign Key, Nullable): For substitutions, references the `id` of the player who came *on*.
        *   `player_out_id` (INTEGER, Foreign Key, Nullable): For substitutions, references the `id` of the player who went *off*.

Together, these tables form the backbone for both recognizing entities within commentary and persisting the structured output of each analysis.

## Preparing Your Input

The application accepts input in three main ways:

1.  **Text File (`commentary.txt`):** Place your plain text Arabic soccer commentary in the `soccer_commentary_analyzer/commentary.txt` file. This is used by the CLI by default.
2.  **YouTube URL:** Provide a YouTube video URL via the CLI (`--youtube-url`) or the API (`POST /v1/analyze-youtube`). The application will download and transcribe the audio automatically.
3.  **Audio/Video File Upload:** Upload an MP3, WAV, or MP4 file via the API (`POST /v1/analyze-media`).

Ensure FFmpeg is installed and accessible in your `PATH` for YouTube or file upload features to work.

## Using the API Server

The FastAPI backend provides a RESTful API for programmatic access and integration.

1.  **Start the Server:**

    From the project's *parent* directory with the virtual environment activated:

    ```bash
    uvicorn soccer_commentary_analyzer.app:app --reload --host 0.0.0.0 --port 8000
    ```

    *   `--reload`: Automatically restarts the server on code changes (useful for development).
    *   `--host 0.0.0.0`: Makes the server accessible from other machines on the network (omit for localhost only).
    *   `--port 8000`: Specifies the port (default is 8000).

2.  **Access the API:**

    *   **Interactive Docs (Swagger UI):** Open your browser and go to `http://localhost:8000/v1/docs`.
    *   **ReDoc Documentation:** `http://localhost:8000/v1/redoc`.

3.  **Common API Endpoints:**

    *   **`GET /v1/teams`**: Retrieve a list of all teams recognized by the system (useful for team selection).
    *   **`POST /v1/analyze` (Form)**:
        *   Analyze text from `commentary.txt`.
        *   Optionally select teams by `home_team_id` and `away_team_id` (get IDs from `/v1/teams`).
        *   Example (using `curl`):
          ```bash
          curl -X POST "http://localhost:8000/v1/analyze" -H  "accept: application/json" -F "home_team_id=1" -F "away_team_id=2"
          ```
    *   **`POST /v1/analyze` (JSON)**:
        *   Similar to Form, but send the full commentary text directly in the JSON body.
        *   Example (using `curl`):
          ```bash
          curl -X POST "http://localhost:8000/v1/analyze" -H  "accept: application/json" -H "Content-Type: application/json" -d '{"commentary": "نص التعليق الكامل هنا...", "home_team_id": 1, "away_team_id": 2}'
          ```
    *   **`POST /v1/analyze-youtube`**:
        *   Analyze commentary from a YouTube URL.
        *   Example (using `curl`):
          ```bash
          curl -X POST "http://localhost:8000/v1/analyze-youtube" -H "accept: application/json" -F "url=https://www.youtube.com/watch?v=YOUR_VIDEO_ID" -F "home_team_id=1" -F "away_team_id=2"
          ```
    *   **`POST /v1/analyze-media`**:
        *   Upload an audio/video file for transcription and analysis.
        *   Example (using `curl`):
          ```bash
          curl -X POST "http://localhost:8000/v1/analyze-media" -H "accept: application/json" -H "Content-Type: multipart/form-data" -F "file=@/path/to/your/audio.mp3" -F "home_team_id=1" -F "away_team_id=2"
          ```

## Workflow Highlights Summary

The analysis follows a multi-stage pipeline to transform commentary into structured data:

1.  **Initialization & Input:**
    *   Commentary text is loaded (from file, YouTube transcription, or direct input).
    *   A database lookup initializes lists of known teams and players.

2.  **Core Analysis Loop (Iterative Refinement):**
    *   The pipeline repeatedly performs stages 3-6 until results are consistent and complete.

3.  **Stage 3: Team Identification:**
    *   Determines the two competing teams from the commentary using an LLM.
    *   Validates team names against the database.

4.  **Stage 4: Player & Event Extraction:**
    *   **Player Extraction:** Identifies players mentioned, attempting to assign them to the home/away teams.
    *   **Event Extraction:** Parses commentary segments to find match events (goals, cards, subs), linking them to (initially extracted) players and teams.

5.  **Stage 5: Data Cleansing & Enrichment:**
    *   **Player Normalization:** Matches extracted player names to canonical names in the database using fuzzy logic.
    *   **Player Deduplication:** Merges potential duplicate player mentions (typos, nicknames).
    *   **Team Composition Enforcement:** Ensures valid team setups (e.g., 11 players, required positions like goalkeeper).
    *   **Event Synchronization:** Aligns event players with the final, validated player list. Attempts to resolve unmatched names using database fuzzy matching or auto-augmenting the roster.

6.  **Stage 6: Validation & Review:**
    *   **Validation:** Checks data consistency (e.g., correct teams, sufficient events, valid substitutions).
    *   **LLM Reviewer:** A separate, more powerful LLM reviews the full context, identifying inconsistencies, suggesting corrections (player merges, event edits, missing players/events), and evaluating overall data quality.
    *   **Iteration Decision:** Based on validation issues or reviewer feedback (e.g., low coverage), the pipeline decides whether to loop back for another pass (e.g., re-extract events with updated player list) or proceed.

7.  **Compilation & Output:**
    *   Once validation passes and the reviewer is satisfied, the final list of events and players is compiled.
    *   Calculates the final match score.
    *   Saves the structured data to Excel and CSV files.
    *   Optionally saves the match data to the SQLite database.

This iterative, multi-step approach with validation and review stages aims to maximize accuracy and completeness by refining data through successive passes.

## Development Notes

*   **Database Initialization:** The application expects a populated `database/teams_players.db`. Scripts in `other/` (like `init_database_with_scraping.py`) can help populate it, but this might require an initial scrape or seed data which isn't included by default. Ensure the database is set up before running analyses for best results.
*   **Log Files:** Logs and metrics are written to `output/logs/`.
*   **Dependencies:** Keep `requirements.txt` updated if you add or change libraries.

---