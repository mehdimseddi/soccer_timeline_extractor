# utils/asr_whisper.py
from __future__ import annotations
import os
import uuid
from pathlib import Path
from typing import List, Tuple

from ..config import logger, OUTPUT_DIR
from .audio_transcription import convert_mp3_to_wav, convert_mp4_to_wav, preprocess_audio
from .arabic import normalize_arabic_text

try:
    from faster_whisper import WhisperModel  # type: ignore
except Exception as e:  # pragma: no cover
    WhisperModel = None  # fallback for environments without the package


_MODEL: WhisperModel | None = None


def _get_model(model_size: str = os.getenv("WHISPER_MODEL", "small")) -> WhisperModel:
    global _MODEL
    if _MODEL is None:
        if WhisperModel is None:
            raise RuntimeError("faster-whisper is not installed. Please add 'faster-whisper' to requirements.")
        # CPU-friendly default
        _MODEL = WhisperModel(model_size, device="cpu", compute_type="int8")
        logger.info(f"Loaded faster-whisper model: {model_size} (cpu, int8)")
    return _MODEL


def _format_ts(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h = ms // 3_600_000
    m = (ms % 3_600_000) // 60_000
    s = (ms % 60_000) // 1000
    ms_rem = ms % 1000
    return f"{h:02d}:{m:02d}:{s:02d}.{ms_rem:03d}"


def _build_vtt_from_words(words: List[Tuple[str, float, float]], max_cue_sec: float = 5.0, max_chars: int = 80) -> str:
    vtt_lines = ["WEBVTT", ""]
    cur_start = None
    cur_end = None
    cur_text_parts: List[str] = []
    cur_chars = 0

    def flush():
        nonlocal cur_start, cur_end, cur_text_parts, cur_chars
        if cur_start is None or cur_end is None or not cur_text_parts:
            return
        text = " ".join(cur_text_parts).strip()
        if not text:
            # reset
            cur_start = None
            cur_end = None
            cur_text_parts = []
            cur_chars = 0
            return
        # Insert RLM for better RTL rendering
        text = "\u200F" + text
        vtt_lines.append(f"{_format_ts(cur_start)} --> {_format_ts(cur_end)}")
        vtt_lines.append(text)
        vtt_lines.append("")
        # reset
        cur_start = None
        cur_end = None
        cur_text_parts = []
        cur_chars = 0

    for token, w_start, w_end in words:
        token = token.strip()
        if not token:
            continue
        if cur_start is None:
            cur_start = w_start
            cur_end = w_end
            cur_text_parts = [token]
            cur_chars = len(token)
            continue
        # Check limits
        new_duration = (w_end - cur_start)
        new_chars = cur_chars + 1 + len(token)
        if new_duration > max_cue_sec or new_chars > max_chars:
            flush()
            cur_start = w_start
            cur_end = w_end
            cur_text_parts = [token]
            cur_chars = len(token)
        else:
            cur_end = w_end
            cur_text_parts.append(token)
            cur_chars = new_chars
    flush()
    return "\n".join(vtt_lines)


def transcribe_with_whisper(file_path: str) -> Tuple[str, str]:
    """
    Transcribe an audio/video file with faster-whisper (Arabic) and return:
    - cleaned transcript text
    - path to a saved WebVTT file
    """
    # Convert to wav if needed
    src = Path(file_path)
    tmp_wav: Path
    if src.suffix.lower() == ".mp4":
        tmp_wav = Path(convert_mp4_to_wav(str(src), Path(src.parent)))
    elif src.suffix.lower() == ".mp3":
        tmp_wav = Path(convert_mp3_to_wav(str(src), Path(src.parent)))
    else:
        tmp_wav = src

    # Optional preprocessing
    clean_wav = Path(preprocess_audio(str(tmp_wav), Path(tmp_wav.parent)))

    model = _get_model()
    segments, info = model.transcribe(
        str(clean_wav),
        language="ar",
        beam_size=5,
        vad_filter=True,
        word_timestamps=True,
        temperature=[0.0, 0.2],
        best_of=5,
        without_timestamps=False,
    )

    full_text_parts: List[str] = []
    words: List[Tuple[str, float, float]] = []

    for seg in segments:
        seg_text = (seg.text or "").strip()
        if seg_text:
            full_text_parts.append(seg_text)
        if getattr(seg, "words", None):
            for w in seg.words:
                token = (w.word or "").strip()
                if not token:
                    continue
                # faster-whisper words include leading space
                words.append((token, float(w.start), float(w.end)))

    raw_text = " ".join(full_text_parts)

    # Lightweight normalization (no semantic edits)
    cleaned = normalize_arabic_text(raw_text)
    cleaned = " ".join(cleaned.split())

    # Build VTT and save
    vtt = _build_vtt_from_words(words)
    out_dir = Path(OUTPUT_DIR) / "vtt"
    out_dir.mkdir(parents=True, exist_ok=True)
    vtt_path = out_dir / f"{uuid.uuid4()}.vtt"
    vtt_path.write_text(vtt, encoding="utf-8")
    logger.info(f"VTT saved: {vtt_path}")

    return cleaned, str(vtt_path)
