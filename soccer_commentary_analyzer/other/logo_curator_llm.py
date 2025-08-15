# other/logo_curator_llm.py
"""
LLM-assisted logo curator (standalone).

- Input: team name (Arabic), candidate image URLs (from Wikidata/Commons/Infobox/official site)
- Output: best logo image downloaded to output/team_logos/curated/
- Keeps decisions in a curation manifest for audit

Requires:
- GOOGLE_API_KEY env var (Gemini 1.5 model with vision)
- langchain-google-genai installed (already in project requirements)

Usage examples:
  python -m soccer_commentary_analyzer.other.logo_curator_llm --team "الترجي الرياضي التونسي" \
    --url "https://upload.wikimedia.org/wikipedia/commons/3/37/Esp%C3%A9rance_Sportive_de_Tunis_logo.svg" \
    --url "https://upload.wikimedia.org/wikipedia/commons/thumb/b/bb/Esperance_Tunis_Building.JPG/330px-Esperance_Tunis_Building.JPG"

  # Or evaluate a text file with one URL per line
  python -m soccer_commentary_analyzer.other.logo_curator_llm --team "النادي الرياضي الصفاقسي" --url-file candidates.txt
"""
from __future__ import annotations
import os
import re
import json
import time
import argparse
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse

import requests
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage

try:
    from ..config import OUTPUT_DIR, logger
except Exception:
    import logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("logo_curator_llm")
    OUTPUT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "output"))

CURATED_DIR = os.path.join(OUTPUT_DIR, "team_logos", "curated")
CURATION_LOG = os.path.join(CURATED_DIR, "curation.jsonl")


@dataclass
class Candidate:
    url: str
    source: str = "manual"


def ensure_dirs() -> None:
    os.makedirs(CURATED_DIR, exist_ok=True)


def slugify(s: str) -> str:
    s = re.sub(r"[^\w\-\u0600-\u06FF]+", "_", s, flags=re.U)
    return re.sub(r"_+", "_", s).strip("_")


def guess_ext_from_url(url: str) -> str:
    path = urlparse(url).path.lower()
    for ext in (".svg", ".png", ".jpg", ".jpeg", ".webp"):
        if path.endswith(ext):
            return ext
    return ".png"


def http_head_ok(url: str) -> bool:
    try:
        r = requests.head(url, timeout=15, allow_redirects=True)
        return r.status_code == 200 and ("image" in r.headers.get("content-type", "").lower())
    except Exception:
        return False


def get_vision_llm(model: str = os.environ.get("GEMINI_VISION_MODEL", "gemini-1.5-flash")):
    # Requires GOOGLE_API_KEY in env
    return ChatGoogleGenerativeAI(model=model, temperature=0.1, max_retries=2, timeout=60)


def judge_logo(team_name: str, url: str, llm) -> Dict[str, Any]:
    """Ask LLM to judge if the image is the club's logo/crest."""
    system_instructions = (
        "You are a strict curator of football club logos. "
        "Given a TEAM NAME (Arabic) and an IMAGE, decide if the image is the club's official crest/logo.\n"
        "Reject photographs of buildings, stadiums, players, fans, kits/jerseys, social headers, or sponsor images.\n"
        "Prefer vector or flat graphic logos (often SVG/PNG), shapes like shields/circles, clear emblem marks.\n"
        "Return pure JSON with fields: {is_logo: bool, confidence: float (0..1), reasons: string, kind: string}.\n"
        "kind should be one of: 'logo', 'kit', 'stadium', 'building', 'player', 'other'."
    )
    content = [
        {
            "type": "text",
            "text": f"TEAM: {team_name}\nNow judge this image URL strictly as the team's official logo/crest or not."
        },
        {"type": "image_url", "image_url": url},
    ]
    msg = HumanMessage(content=content)
    try:
        res = llm.invoke([msg])
        txt = res.content if hasattr(res, "content") else str(res)
        # Try to extract JSON
        data: Dict[str, Any]
        try:
            # Some models wrap JSON in code fences; strip them
            js = re.search(r"\{[\s\S]*\}", txt)
            data = json.loads(js.group(0) if js else txt)
        except Exception:
            # Fallback heuristic
            data = {"is_logo": ("logo" in txt.lower()), "confidence": 0.4, "reasons": txt, "kind": "other"}
        # Normalize
        data.setdefault("is_logo", False)
        data.setdefault("confidence", 0.0)
        data.setdefault("reasons", "")
        data.setdefault("kind", "other")
        return data
    except Exception as e:
        return {"is_logo": False, "confidence": 0.0, "reasons": f"llm_error: {e}", "kind": "error"}


def curate(team: str, candidates: List[Candidate], min_conf: float = 0.70) -> Optional[Dict[str, Any]]:
    ensure_dirs()
    llm = get_vision_llm()

    results: List[Dict[str, Any]] = []
    for c in candidates:
        if not http_head_ok(c.url):
            logger.info(f"Skipping (HEAD not ok): {c.url}")
            continue
        verdict = judge_logo(team, c.url, llm)
        verdict.update({"team": team, "url": c.url, "source": c.source, "ts": int(time.time())})
        results.append(verdict)
        # Log decision
        with open(CURATION_LOG, "a", encoding="utf-8") as logf:
            logf.write(json.dumps(verdict, ensure_ascii=False) + "\n")
        logger.info(f"Judge: {c.url} -> is_logo={verdict['is_logo']} conf={verdict['confidence']:.2f} kind={verdict.get('kind')}")

    if not results:
        return None

    # Pick best by confidence with logo preference
    best = sorted(results, key=lambda d: (1 if d.get("is_logo") else 0, float(d.get("confidence") or 0.0)), reverse=True)[0]
    if not best.get("is_logo") or float(best.get("confidence") or 0.0) < min_conf:
        logger.warning("No candidate met confidence threshold; keeping best anyway for review")

    # Download best
    ext = guess_ext_from_url(best["url"])
    out_name = f"{slugify(team)}_curated{ext}"
    out_path = os.path.join(CURATED_DIR, out_name)
    try:
        with requests.get(best["url"], stream=True, timeout=30) as r:
            r.raise_for_status()
            with open(out_path, "wb") as f:
                for chunk in r.iter_content(8192):
                    if chunk:
                        f.write(chunk)
        logger.info(f"Saved curated logo: {out_path}")
        best["saved_path"] = os.path.relpath(out_path, OUTPUT_DIR)
        return best
    except Exception as e:
        logger.error(f"Download failed for best candidate: {e}")
        return None


def parse_args():
    ap = argparse.ArgumentParser(description="LLM-assisted curation of team logo images")
    ap.add_argument("--team", required=True, help="Arabic team name")
    ap.add_argument("--url", action="append", default=None, help="Candidate image URL (can be repeated)")
    ap.add_argument("--url-file", default=None, help="Text file with one URL per line")
    ap.add_argument("--min-conf", type=float, default=0.70, help="Minimum confidence to accept (default 0.70)")
    return ap.parse_args()


def main():
    args = parse_args()
    urls: List[str] = []
    if args.url:
        urls.extend([u for u in args.url if u])
    if args.url_file and os.path.exists(args.url_file):
        with open(args.url_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    urls.append(line)
    if not urls:
        logger.error("Provide at least one candidate URL via --url/--url-file")
        return 2

    candidates = [Candidate(url=u, source="manual") for u in urls]
    best = curate(args.team, candidates, min_conf=args.min_conf)
    if not best:
        logger.error("No curated logo saved")
        return 1
    print(json.dumps(best, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
