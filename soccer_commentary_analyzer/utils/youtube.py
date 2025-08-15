# utils/youtube.py
from __future__ import annotations

import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from typing import Tuple
from urllib.parse import urlparse

from ..config import logger


class YouTubeDownloadError(Exception):
    """Raised when downloading audio from YouTube fails."""


_YT_DOMAINS = {"youtube.com", "www.youtube.com", "youtu.be", "m.youtube.com"}


def _is_youtube_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            return False
        netloc = parsed.netloc.lower()
        return any(netloc.endswith(domain) for domain in _YT_DOMAINS)
    except Exception:
        return False


@dataclass
class DownloadedAudio:
    wav_path: str
    temp_dir: str

    def cleanup(self) -> None:
        try:
            if self.temp_dir and os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir, ignore_errors=True)
        except Exception:
            pass


def download_youtube_audio_to_wav(url: str) -> DownloadedAudio:
    """
    Download the best available audio stream from a YouTube URL and convert to WAV.

    Returns a DownloadedAudio containing the wav path and the temporary directory
    (call .cleanup() when done, or delete the directory yourself).
    """
    if not url or not _is_youtube_url(url):
        raise YouTubeDownloadError("Invalid YouTube URL provided.")

    try:
        import yt_dlp  # Lazy import to keep base runtime light
    except Exception as e:
        raise YouTubeDownloadError(
            f"yt_dlp is required to download YouTube audio: {e}"
        ) from e

    temp_dir = tempfile.mkdtemp(prefix="yt_audio_")
    output_path = os.path.join(temp_dir, "audio.%(ext)s")

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": output_path,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "wav",
                "preferredquality": "192",
            }
        ],
        # Be quiet but log errors
        "quiet": True,
        "no_warnings": True,
    }

    # Validate ffmpeg availability for postprocessing
    if shutil.which("ffmpeg") is None:
        logger.warning("ffmpeg binary not found in PATH. yt_dlp postprocessing may fail.")

    logger.info("Starting YouTube audio download…")
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except Exception as e:
        # Cleanup on failure
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception:
            pass
        raise YouTubeDownloadError(f"Failed to download audio: {e}") from e

    # Find produced wav
    for file in os.listdir(temp_dir):
        if file.lower().endswith(".wav"):
            wav_path = os.path.join(temp_dir, file)
            logger.info(f"YouTube audio downloaded to {wav_path}")
            return DownloadedAudio(wav_path=wav_path, temp_dir=temp_dir)

    # If we reach here, no wav was found
    try:
        shutil.rmtree(temp_dir, ignore_errors=True)
    except Exception:
        pass
    raise YouTubeDownloadError("WAV file not found after download.")
