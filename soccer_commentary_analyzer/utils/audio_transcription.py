# utils/audio_transcription.py
import os
import tempfile
from pathlib import Path
import shutil
import time
import random
from contextlib import contextmanager

import speech_recognition as sr
from pydub import AudioSegment
from pydub.utils import make_chunks

import librosa
import noisereduce as nr
import soundfile as sf
import numpy as np

from typing import List, Tuple, Dict, Any
from ..config import logger, OUTPUT_DIR
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- Constants ---
CHUNK_LENGTH_MS: int = 30000  # 30 seconds
TARGET_SAMPLE_RATE: int = 16000
NOISE_REDUCTION_PROP: float = 0.75

# Parallelism for SpeechRecognition chunk transcription
MAX_TRANSCRIPTION_WORKERS: int = int(os.getenv("SR_MAX_WORKERS", "6"))
SR_MAX_ATTEMPTS: int = int(os.getenv("SR_MAX_ATTEMPTS", "3"))
SR_RETRY_BASE_MS: int = int(os.getenv("SR_RETRY_BASE_MS", "250"))  # base backoff per attempt

LANGUAGE = "ar-TN"  # Tunisian Arabic

# FAILED_CHUNKS_DIR = Path("failed_chunks")
# FAILED_CHUNKS_DIR.mkdir(exist_ok=True)

@contextmanager
def temporary_audio_dir():
    """
    Context manager to create a unique temporary directory for audio processing.
    Automatically cleans up on exit.
    """
    temp_dir = Path(tempfile.mkdtemp(prefix="transcription_"))
    try:
        logger.debug(f"Created temporary directory: {temp_dir}")
        yield temp_dir
    finally:
        if temp_dir.exists():
            try:
                shutil.rmtree(temp_dir)
                logger.debug(f"Cleaned up temporary directory: {temp_dir}")
            except Exception as e:
                logger.warning(f"Failed to delete temp directory {temp_dir}: {str(e)}")


def convert_mp4_to_wav(video_path: str, output_dir: Path) -> str:
    """Extract audio from MP4 and save as WAV."""
    logger.info("Extracting audio from MP4...")
    audio = AudioSegment.from_file(video_path, format="mp4")
    wav_path = output_dir / "input.wav"
    audio.export(str(wav_path), format="wav", bitrate="192k")
    return str(wav_path)


def convert_mp3_to_wav(mp3_path: str, output_dir: Path) -> str:
    """Convert MP3 to WAV."""
    logger.info("Converting MP3 to WAV...")
    sound = AudioSegment.from_mp3(mp3_path)
    wav_path = output_dir / "input.wav"
    sound.export(str(wav_path), format="wav", bitrate="192k")
    return str(wav_path)


def preprocess_audio(file_path: str, output_dir: Path) -> str:
    """Apply noise reduction and normalization."""
    try:
        logger.info("Preprocessing audio (noise reduction)...")
        audio, sr = librosa.load(file_path, sr=TARGET_SAMPLE_RATE, mono=True)
        audio = nr.reduce_noise(y=audio, sr=TARGET_SAMPLE_RATE, stationary=True,prop_decrease=NOISE_REDUCTION_PROP)
        audio = librosa.util.normalize(audio, norm=np.inf)
        clean_path = output_dir / "clean.wav"
        sf.write(str(clean_path), audio, TARGET_SAMPLE_RATE, subtype='PCM_16')
        return str(clean_path)
    except Exception as e:
        logger.warning(f"Preprocessing failed: {str(e)}, using original audio")
        return file_path


def split_audio_fixed_chunks(audio_path: str, output_dir: Path) -> List[str]:
    """Split audio into fixed-length chunks for transcription."""
    try:
        logger.info("Splitting audio into fixed-length chunks...")
        sound = AudioSegment.from_wav(audio_path)
        chunks = make_chunks(sound, CHUNK_LENGTH_MS)
        chunk_files = []
        chunks_folder = output_dir / "chunks"
        chunks_folder.mkdir(exist_ok=True)

        for i, chunk in enumerate(chunks):
            chunk_path = chunks_folder / f"chunk_{i:04d}.wav"
            chunk.export(str(chunk_path), format="wav", bitrate="192k")
            chunk_files.append(str(chunk_path))

        logger.debug(f"Created {len(chunk_files)} chunks")
        return chunk_files

    except Exception as e:
        logger.error(f"Audio chunking failed: {str(e)}")
        return []


def transcribe_chunk(chunk_path: str, recognizer: sr.Recognizer) -> Tuple[int, str, str]:
    """
    Transcribe a single audio chunk.
    Returns: (index, text, error)
    """
    try:
        with sr.AudioFile(chunk_path) as source:
            audio = recognizer.record(source)
        text = recognizer.recognize_google(audio, language=LANGUAGE)
        return (0, text.strip(), "")  # index will be handled by caller
    except sr.UnknownValueError:
        return (0, "", "Could not understand audio")
    except sr.RequestError as e:
        return (0, "", f"API request failed: {str(e)}")
    except Exception as e:
        return (0, "", f"Unexpected error: {str(e)}")


def _transcribe_chunk_path(index: int, chunk_path: str) -> Tuple[int, str, str]:
    """
    Thread-safe transcription for a chunk path. Creates its own Recognizer instance.
    Returns: (index, text, error)
    """
    local_recognizer = sr.Recognizer()
    try:
        with sr.AudioFile(chunk_path) as source:
            audio = local_recognizer.record(source)
    except Exception as e:
        return (index, "", f"Failed to load audio: {str(e)}")

    # Retry loop for network/transient failures
    for attempt in range(SR_MAX_ATTEMPTS):
        try:
            text = local_recognizer.recognize_google(audio, language=LANGUAGE)
            return (index, (text or "").strip(), "")
        except sr.UnknownValueError:
            # Not retriable: recognizer couldn't understand this audio
            return (index, "", "Could not understand audio")
        except sr.RequestError as e:
            # Retriable: API/network error
            if attempt + 1 < SR_MAX_ATTEMPTS:
                delay = (SR_RETRY_BASE_MS * (2 ** attempt) + random.randint(0, 200)) / 1000.0
                time.sleep(delay)
                continue
            return (index, "", f"API request failed after retries: {str(e)}")
        except Exception as e:
            # Treat as transient, retry a limited number of times
            if attempt + 1 < SR_MAX_ATTEMPTS:
                delay = (SR_RETRY_BASE_MS * (2 ** attempt) + random.randint(0, 200)) / 1000.0
                time.sleep(delay)
                continue
            return (index, "", f"Unexpected error after retries: {str(e)}")


def _transcribe_chunk_path_with_duration(index: int, chunk_path: str) -> Tuple[int, str, str, int]:
    """
    Transcribe a chunk and also return its duration in milliseconds.
    Returns: (index, text, error, duration_ms)
    """
    text = ""
    error = ""
    local_recognizer = sr.Recognizer()
    try:
        with sr.AudioFile(chunk_path) as source:
            audio = local_recognizer.record(source)
    except Exception as e:
        error = f"Failed to load audio: {str(e)}"
        audio = None  # type: ignore

    if audio is not None:
        for attempt in range(SR_MAX_ATTEMPTS):
            try:
                text = (local_recognizer.recognize_google(audio, language=LANGUAGE) or "").strip()
                error = ""
                break
            except sr.UnknownValueError:
                error = "Could not understand audio"
                break
            except sr.RequestError as e:
                error = f"API request failed: {str(e)}"
                if attempt + 1 < SR_MAX_ATTEMPTS:
                    delay = (SR_RETRY_BASE_MS * (2 ** attempt) + random.randint(0, 200)) / 1000.0
                    time.sleep(delay)
                    continue
                break
            except Exception as e:
                error = f"Unexpected error: {str(e)}"
                if attempt + 1 < SR_MAX_ATTEMPTS:
                    delay = (SR_RETRY_BASE_MS * (2 ** attempt) + random.randint(0, 200)) / 1000.0
                    time.sleep(delay)
                    continue
                break
    # Always try to compute duration
    try:
        snd = AudioSegment.from_wav(chunk_path)
        dur_ms = len(snd)
    except Exception:
        dur_ms = CHUNK_LENGTH_MS
    return (index, text, error, dur_ms)


def transcribe_audio_file(file_path: str) -> str:
    """
    Main function to transcribe an audio/video file.
    Supports: .mp3, .wav, .mp4
    Returns: Full transcribed text.
    """
    with temporary_audio_dir() as temp_dir:
        logger.info(f"Starting transcription for {file_path}")

        # Step 1: Convert to WAV if needed
        if file_path.lower().endswith('.mp4'):
            input_wav = convert_mp4_to_wav(file_path, temp_dir)
        elif file_path.lower().endswith('.mp3'):
            input_wav = convert_mp3_to_wav(file_path, temp_dir)
        elif file_path.lower().endswith('.wav'):
            input_wav = file_path
        else:
            raise ValueError("Unsupported file format. Use MP3, WAV, or MP4.")

        # Step 2: Preprocess (noise reduction)
        clean_path = preprocess_audio(input_wav, temp_dir)

        # Step 3: Split into chunks
        chunk_files = split_audio_fixed_chunks(clean_path, temp_dir)
        if not chunk_files:
            raise RuntimeError("No audio chunks were created. Audio may be too short or corrupted.")

        # Step 4: Transcribe chunks (parallelized)
        logger.info(f"Transcribing {len(chunk_files)} chunks with {MAX_TRANSCRIPTION_WORKERS} workers")
        results: List[Tuple[int, str, str]] = []
        with ThreadPoolExecutor(max_workers=MAX_TRANSCRIPTION_WORKERS) as executor:
            futures = {executor.submit(_transcribe_chunk_path, i, cf): i for i, cf in enumerate(chunk_files)}
            for fut in as_completed(futures):
                idx, text, error = fut.result()
                if error:
                    logger.warning(f"Chunk {idx + 1} transcription failed: {error}")
                results.append((idx, text, error))

        # Reassemble transcript in original chunk order
        full_text = ""
        for idx, text, _ in sorted(results, key=lambda t: t[0]):
            if text:
                full_text += " " + text

        if not full_text.strip():
            logger.warning("Transcription produced no text. Audio may be silent or in unsupported language.")

        logger.info(f"Transcription completed successfully: {full_text.strip()}")
        return full_text.strip()


# -------------------------
# VTT BUILDING (Google SR)
# -------------------------

def _fmt_ts(ms: int) -> str:
    ms = max(0, int(ms))
    h = ms // 3_600_000
    m = (ms % 3_600_000) // 60_000
    s = (ms % 60_000) // 1000
    ms_rem = ms % 1000
    return f"{h:02d}:{m:02d}:{s:02d}.{ms_rem:03d}"


def _split_arabic_sentences(text: str) -> List[str]:
    import re
    # Split on Arabic punctuation and common sentence enders, keep content
    parts = re.split(r"(?<=[\.\!\?\u061F\u060C\u2026])\s+|\n+", text)
    return [p.strip() for p in parts if p and p.strip()]


def _wrap_text(text: str, width: int = 40, max_lines: int = 2) -> List[str]:
    words = text.split()
    lines: List[str] = []
    cur = ""
    for w in words:
        if not cur:
            cur = w
        elif len(cur) + 1 + len(w) <= width:
            cur += " " + w
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    if len(lines) <= max_lines:
        return lines
    # If more than max_lines, combine/tighten to fit max_lines
    return lines[:max_lines]


def transcribe_audio_with_chunks(file_path: str) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Transcribe and return:
    - full transcript text
    - list of chunks with timings: [{start_ms, end_ms, text}]
    """
    with temporary_audio_dir() as temp_dir:
        logger.info(f"Starting transcription for {file_path}")

        # Convert to WAV if needed
        if file_path.lower().endswith('.mp4'):
            input_wav = convert_mp4_to_wav(file_path, temp_dir)
        elif file_path.lower().endswith('.mp3'):
            input_wav = convert_mp3_to_wav(file_path, temp_dir)
        elif file_path.lower().endswith('.wav'):
            input_wav = file_path
        else:
            raise ValueError("Unsupported file format. Use MP3, WAV, or MP4.")

        clean_path = preprocess_audio(input_wav, temp_dir)
        chunk_files = split_audio_fixed_chunks(clean_path, temp_dir)
        if not chunk_files:
            raise RuntimeError("No audio chunks were created. Audio may be too short or corrupted.")

        # Parallelize chunk transcription with duration
        logger.info(f"Transcribing {len(chunk_files)} chunks with {MAX_TRANSCRIPTION_WORKERS} workers (with durations)")
        results2: List[Tuple[int, str, str, int]] = []
        with ThreadPoolExecutor(max_workers=MAX_TRANSCRIPTION_WORKERS) as executor:
            futures = {executor.submit(_transcribe_chunk_path_with_duration, i, cf): i for i, cf in enumerate(chunk_files)}
            for fut in as_completed(futures):
                idx, text, error, dur_ms = fut.result()
                if error:
                    logger.warning(f"Chunk {idx + 1} transcription failed: {error}")
                results2.append((idx, (text or "").strip(), error, int(dur_ms)))

        # Reassemble in order and build cues
        full_text_parts: List[str] = []
        chunks_out: List[Dict[str, Any]] = []
        for idx, text, _err, dur_ms in sorted(results2, key=lambda r: r[0]):
            start_ms = idx * CHUNK_LENGTH_MS
            end_ms = start_ms + int(dur_ms)
            if text:
                full_text_parts.append(text)
            chunks_out.append({"start_ms": start_ms, "end_ms": end_ms, "text": text})

        transcript = " ".join(full_text_parts).strip()
        if not transcript:
            logger.warning("Transcription produced no text. Audio may be silent or in unsupported language.")
        logger.info("Transcription complete")
        return transcript, chunks_out


def build_vtt_from_chunks(chunks: List[Dict[str, Any]], match_id: str = None) -> str:
    """
    Build a WebVTT string from chunked text and timings (no word timestamps).
    Saves the VTT under output/{match_id}/commentary.vtt if match_id provided,
    otherwise output/vtt/{uuid}.vtt. Returns the saved path.
    """
    import uuid as _uuid
    from pathlib import Path

    MIN_CUE_MS = 2500
    MAX_CUE_MS = 6000
    GAP_MS = 80
    MAX_LINE = 40
    MAX_LINES = 2
    MAX_CPS = 17.0

    vtt_lines: List[str] = ["WEBVTT", ""]
    last_end = 0

    def cps_ok(text: str, dur_ms: int) -> bool:
        chars = max(1, len(text))
        dur_s = max(0.001, dur_ms / 1000.0)
        return (chars / dur_s) <= MAX_CPS

    for chunk in chunks:
        c_start = int(chunk["start_ms"]) or 0
        c_end = int(chunk["end_ms"]) or (c_start + CHUNK_LENGTH_MS)
        c_text = (chunk.get("text") or "").strip()
        if not c_text:
            continue
        sentences = _split_arabic_sentences(c_text)
        if not sentences:
            sentences = [c_text]
        total_chars = max(1, sum(len(s) for s in sentences))
        available = max(0, c_end - c_start)
        t = max(c_start, last_end + GAP_MS)
        for s in sentences:
            alloc = int(available * (len(s) / total_chars))
            alloc = max(MIN_CUE_MS, min(MAX_CUE_MS, alloc))
            t0 = max(t, last_end + GAP_MS)
            t1 = t0 + alloc
            wrapped = _wrap_text(s, width=MAX_LINE, max_lines=MAX_LINES)
            joined = " ".join(wrapped)
            # if cps too high, try to increase within cap
            if not cps_ok(joined, alloc) and alloc < MAX_CUE_MS:
                extra = min(MAX_CUE_MS - alloc, 1000)
                t1 = t0 + alloc + extra
                alloc += extra
            vtt_lines.append(f"{_fmt_ts(t0)} --> {_fmt_ts(t1)}")
            for line in wrapped:
                vtt_lines.append("\u200F" + line)
            vtt_lines.append("")
            last_end = t1
            t = t1

    # Save VTT
    if match_id:
        out_dir = Path(OUTPUT_DIR) / match_id
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "commentary.vtt"
    else:
        out_dir = Path(OUTPUT_DIR) / "vtt"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{_uuid.uuid4()}.vtt"
    out_path.write_text("\n".join(vtt_lines), encoding="utf-8")
    logger.info(f"VTT saved: {out_path}")
    return str(out_path)


def build_cues_from_chunks(chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return canonical cues built from chunk timings and text.
    Each cue: {start_ms, end_ms, text}
    """
    MIN_CUE_MS = 2500
    MAX_CUE_MS = 6000
    GAP_MS = 80

    cues: List[Dict[str, Any]] = []
    last_end = 0
    for chunk in chunks:
        c_start = int(chunk["start_ms"]) or 0
        c_end = int(chunk["end_ms"]) or (c_start + CHUNK_LENGTH_MS)
        c_text = (chunk.get("text") or "").strip()
        if not c_text:
            continue
        sentences = _split_arabic_sentences(c_text)
        if not sentences:
            sentences = [c_text]
        total_chars = max(1, sum(len(s) for s in sentences))
        available = max(0, c_end - c_start)
        t = max(c_start, last_end + GAP_MS)
        for s in sentences:
            alloc = int(available * (len(s) / total_chars))
            alloc = max(MIN_CUE_MS, min(MAX_CUE_MS, alloc))
            t0 = max(t, last_end + GAP_MS)
            t1 = t0 + alloc
            cues.append({"start_ms": t0, "end_ms": t1, "text": s})
            last_end = t1
            t = t1
    return cues


def vtt_text_from_cues(cues: List[Dict[str, Any]]) -> str:
    """Build VTT text from canonical cues without saving to disk."""
    lines = ["WEBVTT", ""]
    for cue in cues:
        t0 = _fmt_ts(int(cue["start_ms"]))
        t1 = _fmt_ts(int(cue["end_ms"]))
        text = (cue.get("text") or "").strip()
        if not text:
            continue
        wrapped = _wrap_text(text, width=40, max_lines=2)
        lines.append(f"{t0} --> {t1}")
        for w in wrapped:
            lines.append("\u200F" + w)
        lines.append("")
    return "\n".join(lines)