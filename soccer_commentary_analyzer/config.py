# config.py
import os
from datetime import datetime
from langchain_google_genai import ChatGoogleGenerativeAI
import logging
from logging.handlers import RotatingFileHandler
import sys
from dotenv import load_dotenv

load_dotenv()  # loads .env from current working directory

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

# Root logger configuration with optional rotating file handler
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
root_logger = logging.getLogger()
root_logger.setLevel(LOG_LEVEL)

logger = logging.getLogger(__name__)

LLM_MODEL_LITE_NAME = "gemini-2.5-flash-lite"
LLM_MODEL_NAME = "gemini-2.5-pro"
TEMPERATURE = 0.1

MAX_RETRIES = 3  # Maximum number of retries per chunk
RETRY_DELAY = 1  # Optional delay (seconds) between retries
EVENT_CONFIDENCE_THRESHOLD = float(os.getenv("EVENT_CONFIDENCE_THRESHOLD", "0.5"))

# New player resolution policy flags
STRICT_ROSTER_ENFORCEMENT = os.getenv("STRICT_ROSTER_ENFORCEMENT", "false").lower() == "true"
DB_MATCH_THRESHOLD = int(os.getenv("DB_MATCH_THRESHOLD", "88"))
AUTO_AUGMENT_ROSTER = os.getenv("AUTO_AUGMENT_ROSTER", "true").lower() == "true"
MAX_AUTO_AUGMENT = int(os.getenv("MAX_AUTO_AUGMENT", "2"))
MIN_CONFIDENCE_TO_KEEP_UNRESOLVED = float(os.getenv("MIN_CONFIDENCE_TO_KEEP_UNRESOLVED", "0.35"))

# Disallowed team names (coach/person names) to steer LLM away from invalid teams
_default_disallowed = [
    # Common Tunisian coaches / public figures often confused as team names
    "فوزي البنزرتي", "فوزي بنزرتي", "منذر الكبير", "نبيل معلول", "عادل السليمي",
    "لسعد الدريدي", "أحمد العجلاني", "قيس اليعقوبي", "سعيد السايبي",
]
DISALLOWED_TEAM_NAMES = [s.strip() for s in os.getenv("DISALLOWED_TEAM_NAMES", ",".join(_default_disallowed)).split(",") if s.strip()]



# Build an absolute path to the database file
_project_root = os.path.dirname(__file__)
DATABASE_DIR = os.path.join(_project_root, "database")
DATABASE_PATH = os.path.join(DATABASE_DIR, "teams_players.db")
COMMENTARY_PATH = os.path.join(_project_root, "commentary.txt")

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
OUTPUT_DIR = os.path.join(_project_root, "output")
TEMP_DIR = os.path.join(_project_root, "temp")

# Instrumentation
METRICS_ENABLED = os.getenv("METRICS_ENABLED", "1") == "1"
METRICS_FLUSH_TO_FILE = os.getenv("METRICS_FLUSH_TO_FILE", "1") == "1"
METRICS_FILE = os.path.join(OUTPUT_DIR, "logs", "metrics.log")

# Ensure important directories exist
os.makedirs(DATABASE_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)
os.makedirs(os.path.join(OUTPUT_DIR, "logs"), exist_ok=True)

# Add rotating file handler for logs
try:
    log_file = os.path.join(OUTPUT_DIR, "logs", "app.log")
    if not any(isinstance(h, RotatingFileHandler) for h in root_logger.handlers):
        file_handler = RotatingFileHandler(log_file, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
        file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
        root_logger.addHandler(file_handler)
except Exception as _e:
    # Fall back silently if file logging cannot be set up
    logger.debug(f"Skipping file logging setup: {_e}")


def _require_google_api_key():
    if not os.getenv("GOOGLE_API_KEY"):
        raise RuntimeError(
            "GOOGLE_API_KEY is not set. Please export it in your environment."
        )


# Factory for Gemini LLM with retries and timeout
def get_gemini_llm(temperature: float = TEMPERATURE, max_retries: int = MAX_RETRIES, model_name: str = LLM_MODEL_LITE_NAME):
    _require_google_api_key()
    llm = ChatGoogleGenerativeAI(
        model=model_name,
        temperature=temperature,
        max_retries=max_retries,
        timeout=45,
    )
    return llm

# ============================
# API and server configuration
# ============================
API_VERSION = os.getenv("API_VERSION", "v1")

# CORS origins (comma-separated)
ALLOW_ORIGINS = [
    origin.strip()
    for origin in os.getenv("ALLOW_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",")
    if origin.strip()
]

# Limits
MAX_COMMENTARY_CHARS = int(os.getenv("MAX_COMMENTARY_CHARS", "10000000"))
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "100000"))

ALLOWED_EXTENSIONS = {ext.strip().lower() for ext in os.getenv("ALLOWED_EXTENSIONS", ".mp3,.wav,.mp4").split(",") if ext.strip()}
ALLOWED_MIME_TYPES = {mt.strip().lower() for mt in os.getenv("ALLOWED_MIME_TYPES", "audio/mpeg,audio/wav,video/mp4,audio/mp4").split(",") if mt.strip()}

# Artifacts serving base path (URL). We serve via /{API_VERSION}/artifacts/...
ARTIFACTS_ROUTE_PREFIX = f"/{API_VERSION}/artifacts"