# app.py - FastAPI Backend
import logging
from fastapi import FastAPI, HTTPException, File, UploadFile, Form, Depends, BackgroundTasks
from contextlib import asynccontextmanager
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Set
from datetime import datetime
import uuid
import os

# Your existing modules
from .graph.workflow import build_soccer_analysis_graph
from .models.schemas import MatchAnalysis
from .config import (
    DATABASE_PATH,
    COMMENTARY_PATH,
    OUTPUT_DIR,
    logger,
    API_VERSION,
    ALLOW_ORIGINS,
    MAX_COMMENTARY_CHARS,
    MAX_UPLOAD_MB,
    ALLOWED_EXTENSIONS,
    ALLOWED_MIME_TYPES,
    ARTIFACTS_ROUTE_PREFIX,
)
from .utils.db_utils import get_all_team_names
from .utils.visualization import save_analysis_to_excel, save_analysis_to_csv
from .utils.match_utils import compute_match_score
from .utils.db_setup import setup_enum_tables
from .utils.db_operations import get_db_connection, get_team_name_by_id
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from .utils.arabic import normalize_arabic_text

# Initialize FastAPI app
# Lifespan handler replaces deprecated on_event startup/shutdown
@asynccontextmanager
async def app_lifespan(app: FastAPI):
    setup_enum_tables()
    logger.info("Database enum tables initialized.")
    yield
    # Place shutdown cleanup here if needed


app = FastAPI(
    title="Soccer Commentary Analyzer API",
    description="An AI-powered backend to extract match events from Arabic soccer commentary.",
    version="1.0.0",
    openapi_url=f"/{API_VERSION}/openapi.json",
    docs_url=f"/{API_VERSION}/docs",
    redoc_url=f"/{API_VERSION}/redoc",
    lifespan=app_lifespan,
)

# CORS - Allow frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOW_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files (serve OUTPUT_DIR under ARTIFACTS_ROUTE_PREFIX)
try:
    app.mount(ARTIFACTS_ROUTE_PREFIX, StaticFiles(directory=OUTPUT_DIR), name="artifacts")
except Exception:
    # Config normally ensures directories exist; ignore if not present at import time
    pass

graph = build_soccer_analysis_graph()
# ================
# Pydantic Models
# ================

class AnalyzeRequest(BaseModel):
    commentary: Optional[str] = Field(None, description="Full commentary text to analyze")
    home_team_id: Optional[int] = Field(None, description="DB id for home team")
    away_team_id: Optional[int] = Field(None, description="DB id for away team")

class Artifacts(BaseModel):
    excel: str
    events_csv: str
    players_csv: str
    vtt: Optional[str] = Field(None, description="Path to generated WebVTT file")


class AnalyzeResponse(BaseModel):
    match_id: str
    home_team: str
    away_team: str
    score: Dict[str, int]
    counts: Dict[str, int]
    latency_ms: Optional[int] = Field(None, description="Total processing time in milliseconds")
    usage: Optional[Dict[str, int]] = Field(None, description="Estimated token usage and LLM calls")
    artifacts: Artifacts
    analysis: MatchAnalysis
    commentary: Optional[str] = Field(None, description="Transcribed commentary")
    transcript_cues: Optional[List[Dict[str, Any]]] = Field(None, description="Canonical transcript cues for UI rendering")
    # Optional expansions
    home_team_logo_url: Optional[str] = Field(None, description="Public URL to home team logo (if requested via expand)")
    away_team_logo_url: Optional[str] = Field(None, description="Public URL to away team logo (if requested via expand)")


# ================
# API Endpoints
# ================

@app.get(f"/{API_VERSION}/")
def read_root():
    return {
        "message": "مرحباً بكم في نظام تحليل التعليق الرياضي",
        "endpoints": {
            "/teams": "GET - Get all available teams",
            "/analyze": "POST - Analyze commentary (form or JSON)",
            "/analyze/file": "POST - Upload commentary.txt file"
        }
    }


@app.get(f"/{API_VERSION}/teams")
def get_teams():
    """Return list of all teams with ids and names."""
    try:
        from .utils.db_operations import get_db_connection, list_teams
        with get_db_connection() as conn:
            teams = list_teams(conn)
        if not teams:
            raise HTTPException(status_code=404, detail="لم يتم العثور على الفرق")
        return teams
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to load teams: {e}")
        raise HTTPException(status_code=500, detail="تعذر تحميل قائمة الفرق")


def _select_team_logo_url(team_name: Optional[str]) -> Optional[str]:
    """Prefer curated logo, else heuristic manifest; return public artifacts URL."""
    if not team_name:
        return None
    try:
        import json as _json
        # Heuristic manifest
        manifest_path = os.path.join(OUTPUT_DIR, "team_logos", "manifest.json")
        if os.path.exists(manifest_path):
            m = _json.loads(open(manifest_path, "r", encoding="utf-8").read())
            info = m.get(team_name)
            if info and info.get("path"):
                rel = info["path"].lstrip("/\\").replace("\\", "/")
                return f"{ARTIFACTS_ROUTE_PREFIX}/{rel}"
            logger.warning(f"Manifest entry for {team_name} not found or incomplete: {info}")
    except Exception:
        pass
    return None

@app.get(f"/{API_VERSION}/history")
def get_analysis_history():
    try:
        with get_db_connection() as conn:
            rows = conn.execute("""
                SELECT 
                    m.uuid,
                    ht.name AS home_team,
                    at.name AS away_team,
                    m.match_date
                FROM Match m
                JOIN Team ht ON m.home_team_id = ht.id
                JOIN Team at ON m.away_team_id = at.id
                WHERE m.uuid IS NOT NULL
                ORDER BY m.match_date DESC
            """).fetchall()

        history = [
            {
                "match_id": r[0],
                "home_team": r[1],
                "away_team": r[2],
                "match_date": r[3]
            }
            for r in rows
        ]
        return {"history": history}
    except Exception as e:
        logger.error(f"Failed to fetch history: {e}")
        raise HTTPException(status_code=500, detail="Could not retrieve analysis history")
    
@app.post(f"/{API_VERSION}/analyze", response_model=AnalyzeResponse)
def analyze_commentary(request: AnalyzeRequest, expand: Optional[str] = None):
    try:
        home_team: Optional[str] = None
        away_team: Optional[str] = None

        with get_db_connection() as conn:
            # 🔎 Validate and resolve team names
            if request.home_team_id:
                home_name = get_team_name_by_id(conn, request.home_team_id)
                if not home_name:
                    raise HTTPException(status_code=400, detail=f"معرّف الفريق المضيف غير صالح: {request.home_team_id}")
                home_team = home_name

            if request.away_team_id:
                away_name = get_team_name_by_id(conn, request.away_team_id)
                if not away_name:
                    raise HTTPException(status_code=400, detail=f"معرّف الفريق الضيف غير صالح: {request.away_team_id}")
                away_team = away_name
        
        # ✅ Use provided commentary or fallback to default file
        if request.commentary:
            commentary = request.commentary.strip()
            if len(commentary) > MAX_COMMENTARY_CHARS:
                raise HTTPException(status_code=413, detail=f"Commentary too long (>{MAX_COMMENTARY_CHARS} chars)")
        else:
            if not os.path.exists(COMMENTARY_PATH):
                raise HTTPException(status_code=400, detail="تعذر العثور على ملف التعليق commentary.txt")
            with open(COMMENTARY_PATH, "r", encoding="utf-8") as file:
                commentary = file.read()

        # Run analysis
        match_uuid = str(uuid.uuid4())
        
        initial_state = {
            "match_uuid": match_uuid,
            "original_commentary":  commentary,
            "teams": {
                "home_team": home_team,
                "away_team": away_team,
                "confidence": 1.0
            } if home_team and away_team else None,
            "validation_issues": [],
            "attempts": 0,
            "predefined_teams": get_all_team_names(DATABASE_PATH),
        }

        logger.info("Invoking analysis graph")
        from time import perf_counter
        t0 = perf_counter()
        final_state = graph.invoke(initial_state)
        latency_ms = int((perf_counter() - t0) * 1000)
        # Validate result structure
        if not final_state or "final_analysis" not in final_state:
            raise ValueError("Graph did not return valid analysis result")

        if "events" not in final_state["final_analysis"]:
            raise ValueError("No events extracted from commentary")
        
        match_analysis = MatchAnalysis(**final_state["final_analysis"])
        # Final safety: deduplicate players by normalized (name, team) before returning
        try:
            seen_keys = set()
            deduped_players = []
            for p in (match_analysis.players or []):
                norm_name = " ".join(normalize_arabic_text((p.name or "")).lower().split())
                norm_team = (p.team or "").strip()
                key = (norm_name, norm_team)
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                deduped_players.append(p)
            if match_analysis.players is not None and len(deduped_players) != len(match_analysis.players):
                logger.info(f"API dedup removed {len(match_analysis.players) - len(deduped_players)} duplicate players from response")
            match_analysis = MatchAnalysis(events=match_analysis.events, players=deduped_players)
        except Exception:
            # Non-fatal: if anything goes wrong, return as-is
            pass
        home = final_state["teams"]["home_team"]
        away = final_state["teams"]["away_team"]

        # Compute score
        score = compute_match_score(match_analysis.events, home_team=home, away_team=away) or {home: 0, away: 0}

        # Save analysis
        analysis_results = {
            'match_info': {
                'match_id': match_uuid,
                'home_team': home,
                'away_team': away,
                'date': datetime.now().strftime("%Y-%m-%d")
            },
            'events': match_analysis.events,
            'players': match_analysis.players
        }

        xlsx_path = save_analysis_to_excel(analysis_results)
        events_csv, players_csv = save_analysis_to_csv(analysis_results)

        # Save plain-text transcript
        match_id = analysis_results['match_info']['match_id']
        txt_path = os.path.join(OUTPUT_DIR, match_id, "commentary.txt")
        os.makedirs(os.path.dirname(txt_path), exist_ok=True)
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(commentary)

        logger.info(
            f"Analysis complete: events={len(match_analysis.events)}, players={len(match_analysis.players)}"
        )


        resp = AnalyzeResponse(
            match_id=analysis_results['match_info']['match_id'],
            home_team=home,
            away_team=away,
            score={k: v for k, v in score.items()},
            counts={
                "events": len(match_analysis.events),
                "players": len(match_analysis.players or []),
            },
            latency_ms=latency_ms,
            usage=final_state.get("usage", None),
            artifacts=Artifacts(
                excel=xlsx_path,
                events_csv=events_csv,
                players_csv=players_csv,
            ),
            analysis=match_analysis,
        )
        # Optional expansions
        try:
            expansions: Set[str] = set()
            if expand:
                expansions = {e.strip().lower() for e in expand.split(',') if e.strip()}
            if 'logos' in expansions:
                logger.info("Expanding team logos in response")
                resp = resp.model_copy(update={
                    "home_team_logo_url": _select_team_logo_url(home),
                    "away_team_logo_url": _select_team_logo_url(away),
                })
        except Exception:
            pass
        logger.info(f"Analysis response: {resp.model_dump_json(indent=2)}")
        return resp

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Analysis failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error during analysis: {str(e)}")

import tempfile

from .utils.audio_transcription import (
    transcribe_audio_file,
    transcribe_audio_with_chunks,
    build_vtt_from_chunks,
    build_cues_from_chunks,
)
from .utils.youtube import download_youtube_audio_to_wav, YouTubeDownloadError

# Configurable settings
MAX_FILE_SIZE_MB = 100
ALLOWED_EXTENSIONS = {".mp3", ".wav", ".mp4"}
ALLOWED_MIME_TYPES = {"audio/mpeg", "audio/wav", "video/mp4", "audio/mp4"}

@app.post(f"/{API_VERSION}/analyze-media/")
async def analyze_audio_commentary(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    home_team_id: Optional[int] = Form(default=None),
    away_team_id: Optional[int] = Form(default=None),
    expand: Optional[str] = None,
):
    """
    Upload an audio/video file (MP3, WAV, MP4).
    The system will:
      1. Validate & store the file temporarily
      2. Transcribe the audio
      3. Analyze the soccer commentary
    """
    try:
        # ✅ Step 1: Validate MIME type
        if (file.content_type or '').lower() not in ALLOWED_MIME_TYPES:
            raise HTTPException(
                400, 
                f"Unsupported file type '{file.content_type}'. Allowed types: {', '.join(ALLOWED_EXTENSIONS)}"
            )

        # ✅ Step 2: Validate extension
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                400,
                f"Invalid file extension '{ext}'. Allowed extensions: {', '.join(ALLOWED_EXTENSIONS)}"
            )

        # ✅ Step 3: Save file to temp securely
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp_file:
            content = await file.read()

            # ✅ Step 4: Check file size
            file_size_mb = len(content) / (1024 * 1024)
            if file_size_mb > MAX_UPLOAD_MB:
                raise HTTPException(413, f"File too large. Max allowed size is {MAX_FILE_SIZE_MB}MB")

            tmp_file.write(content)
            temp_file_path = tmp_file.name

        logger.info(f"Temporary file saved at {temp_file_path} ({file_size_mb:.2f} MB)")

        # ✅ Step 5: Transcribe audio (capture chunks for VTT)
        logger.info(f"Transcribing file: {file.filename}")
        raw_text, chunks = transcribe_audio_with_chunks(temp_file_path)

        if not raw_text:
            raise HTTPException(
                422, 
                "Could not transcribe audio. The file may be silent or in an unsupported language."
            )

        # ✅ Step 6: Prepare request for analysis
        request = AnalyzeRequest(
            commentary=raw_text,
            home_team_id=home_team_id,
            away_team_id=away_team_id,
        )

        # ✅ Step 7: Reuse existing logic
        response = analyze_commentary(request, expand=expand)
        # Build canonical cues and VTT; attach
        vtt_path = build_vtt_from_chunks(chunks, match_id=response.match_id)
        cues = build_cues_from_chunks(chunks)
        updated_artifacts = response.artifacts.model_copy(update={"vtt": vtt_path})
        response = response.model_copy(update={"artifacts": updated_artifacts, "commentary": raw_text, "transcript_cues": cues})

        # Cleanup temp file after response
        background_tasks.add_task(os.remove, temp_file_path)
        return response

    except HTTPException:
        raise  # re-raise controlled HTTP errors

    except Exception as e:
        logger.error(f"Error in analyze_audio_commentary: {str(e)}", exc_info=True)
        raise HTTPException(500, "Internal server error during audio analysis")

    # finally:
    #     # ✅ Step 8: Cleanup temp file safely
    #     try:
    #         if "temp_file_path" in locals() and os.path.exists(temp_file_path):
    #             # In case background task didn't run
    #             os.remove(temp_file_path)
    #     except Exception:
    #         pass


@app.post(f"/{API_VERSION}/analyze-youtube", response_model=AnalyzeResponse)
def analyze_youtube(
    url: str = Form(..., description="YouTube video URL"),
    home_team_id: Optional[int] = Form(default=None),
    away_team_id: Optional[int] = Form(default=None),
    expand: Optional[str] = None,
):
    """
    Download audio from a YouTube URL, transcribe it, then analyze the commentary.
    """
    try:
        # --- Step 1: Validate and resolve team IDs (reuse DB function) ---
        with get_db_connection() as conn:
            home_team = get_team_name_by_id(conn, home_team_id) if home_team_id else None
            away_team = get_team_name_by_id(conn, away_team_id) if away_team_id else None

            if home_team_id and not home_team:
                raise HTTPException(400, f"معرّف الفريق المضيف غير صالح: {home_team_id}")
            if away_team_id and not away_team:
                raise HTTPException(400, f"معرّف الفريق الضيف غير صالح: {away_team_id}")

        # --- Step 2: Download YouTube audio ---
        try:
            dl = download_youtube_audio_to_wav(url)
        except YouTubeDownloadError as e:
            raise HTTPException(400, str(e))

        # --- Step 3: Transcribe ---
        try:
            raw_text, chunks = transcribe_audio_with_chunks(dl.wav_path)
        finally:
            dl.cleanup()

        if not raw_text:
            raise HTTPException(422, "Could not transcribe audio from YouTube URL.")

        # --- Step 4: Reuse existing analysis logic ---
        request = AnalyzeRequest(
            commentary=raw_text,
            home_team_id=home_team_id,
            away_team_id=away_team_id,
        )
        response = analyze_commentary(request, expand=expand)
        vtt_path = build_vtt_from_chunks(chunks, match_id=response.match_id)
        cues = build_cues_from_chunks(chunks)
        updated_artifacts = response.artifacts.model_copy(update={"vtt": vtt_path})
        return response.model_copy(update={"artifacts": updated_artifacts, "commentary": raw_text, "transcript_cues": cues})

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in analyze_youtube: {str(e)}", exc_info=True)
        raise HTTPException(500, "Internal server error during YouTube analysis")
