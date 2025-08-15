import json
import time
from typing import Any, Dict, Optional
from . import __init__  # noqa: F401
from ..config import METRICS_ENABLED, METRICS_FLUSH_TO_FILE, METRICS_FILE, logger


class Metrics:
    def __init__(self):
        self.enabled = METRICS_ENABLED
        self.flush_to_file = METRICS_FLUSH_TO_FILE
        self.file = METRICS_FILE

    def emit(self, name: str, fields: Optional[Dict[str, Any]] = None):
        if not self.enabled:
            return
        payload = {
            "ts": int(time.time() * 1000),
            "name": name,
            **(fields or {}),
        }
        if self.flush_to_file and self.file:
            try:
                with open(self.file, "a", encoding="utf-8") as f:
                    f.write(json.dumps(payload, ensure_ascii=False) + "\n")
            except Exception as e:
                logger.debug(f"Failed to write metrics: {e}")
        else:
            logger.info(f"METRIC {name}: {payload}")


metrics = Metrics()
