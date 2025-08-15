# other/fetch_team_logos_curated.py
from __future__ import annotations
import os
import time
import json
import argparse
import sqlite3
from typing import List, Dict, Any, Optional, Tuple

try:
    from ..config import OUTPUT_DIR, DATABASE_PATH, logger
except Exception:
    import logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("fetch_team_logos_curated")
    OUTPUT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "output"))
    DATABASE_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "database", "teams_players.db"))

# Reuse helpers from the heuristic fetcher
from .fetch_team_logos import (
    LOGO_DIR,
    ensure_dirs,
    wiki_search_ar,
    get_wikidata_qid_from_ar_wikipedia,
    sparql_p154_preferred,
    _wikidata_claims,
    pick_best_from_claims,
    get_thumbnail_url_from_commons,
    commons_search_logo_candidates,
    parse_infobox_logo_from_ar_wikipedia,
    _http_get,
    slugify,
)
from urllib.parse import urlparse

# LLM curator (optional)
from .logo_curator_llm import curate as llm_curate, Candidate as CuratorCandidate


CURATED_DIR = os.path.join(OUTPUT_DIR, "team_logos", "curated")
CURATED_MANIFEST = os.path.join(CURATED_DIR, "manifest.json")


def load_manifest() -> Dict[str, Any]:
    ensure_dirs()
    if os.path.exists(CURATED_MANIFEST):
        try:
            with open(CURATED_MANIFEST, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_manifest(m: Dict[str, Any]) -> None:
    ensure_dirs()
    tmp = CURATED_MANIFEST + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(m, f, ensure_ascii=False, indent=2)
    os.replace(tmp, CURATED_MANIFEST)


def list_db_teams(db_path: str) -> List[str]:
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT name FROM Team ORDER BY name ASC")
        return [r[0] for r in cur.fetchall()]
    finally:
        conn.close()


def collect_candidates(team: str, width: int = 256, max_search: int = 8) -> List[Tuple[str, str]]:
    """
    Return list of (url, source) candidates in decreasing priority order.
    Sources: p154, p18, infobox, commons:search
    """
    candidates: List[Tuple[str, str]] = []
    title = wiki_search_ar(team) or team
    qid = get_wikidata_qid_from_ar_wikipedia(title)

    if qid:
        # P154 via SPARQL
        p154 = sparql_p154_preferred(qid)
        for fn in p154:
            url = get_thumbnail_url_from_commons(fn, width=width)
            if url:
                candidates.append((url, "wikidata:P154"))
        # Fallback to claims
        if not p154:
            claims = _wikidata_claims(qid)
            fn = pick_best_from_claims(claims)
            if fn:
                url = get_thumbnail_url_from_commons(fn, width=width)
                if url:
                    candidates.append((url, "wikidata:P154"))
        # P18 as last-resort from Wikidata
        # We'll reuse claims to get P18 if present
        if not candidates:
            claims = _wikidata_claims(qid)
            try:
                p18 = claims.get("P18", [])
                if p18:
                    fn18 = p18[0]["mainsnak"]["datavalue"]["value"]
                    url = get_thumbnail_url_from_commons(fn18, width=width)
                    if url:
                        candidates.append((url, "wikidata:P18"))
            except Exception:
                pass

    # Arabic infobox logo param
    infobox = parse_infobox_logo_from_ar_wikipedia(title)
    if infobox:
        candidates.append((infobox, "infobox"))

    # Commons search: team + logo
    for title_fn in commons_search_logo_candidates(team, limit=max_search):
        url = get_thumbnail_url_from_commons(title_fn, width=width)
        if url:
            candidates.append((url, "commons:search"))

    # Deduplicate by URL while preserving order
    seen = set()
    unique: List[Tuple[str, str]] = []
    for url, src in candidates:
        if url in seen:
            continue
        seen.add(url)
        unique.append((url, src))
    return unique


def main():
    ap = argparse.ArgumentParser(description="Curated team logo fetch (Wikidata/Commons + LLM judge)")
    ap.add_argument("--teams", nargs="*", default=None, help="Arabic team names")
    ap.add_argument("--all-db", action="store_true", help="Fetch for all DB teams")
    ap.add_argument("--db", default=DATABASE_PATH, help="SQLite DB path")
    ap.add_argument("--width", type=int, default=256, help="Thumbnail width")
    ap.add_argument("--sleep", type=float, default=0.4, help="Sleep between teams")
    ap.add_argument("--min-conf", type=float, default=0.75, help="LLM min confidence")
    ap.add_argument("--max-search", type=int, default=8, help="Max Commons search candidates")
    args = ap.parse_args()

    if not args.teams and not args.all_db:
        ap.error("Provide --teams or --all-db")

    if args.all_db:
        teams = list_db_teams(args.db)
    else:
        teams = args.teams or []

    ensure_dirs()
    manifest = load_manifest()

    for team in teams:
        try:
            cands = collect_candidates(team, width=args.width, max_search=args.max_search)
            logger.info(f"Candidates for {team}: {len(cands)}")
            if not cands:
                logger.warning(f"No candidates found for {team}")
                continue
            # LLM curate
            curator_in = [CuratorCandidate(url=u, source=s) for u, s in cands]
            best = llm_curate(team, curator_in, min_conf=args.min_conf)
            if best and best.get("saved_path"):
                rel = best["saved_path"]
                manifest[team] = {
                    "team": team,
                    "path": rel,
                    "source": best.get("source", "curated"),
                    "confidence": best.get("confidence"),
                    "url": best.get("url"),
                    "ts": int(time.time()),
                }
                save_manifest(manifest)
                logger.info(f"Curated logo saved: {os.path.join(OUTPUT_DIR, rel)}")
            else:
                logger.warning(f"Curator failed for {team}; no saved logo")
        except Exception as e:
            logger.warning(f"Failed to curate {team}: {e}")
        time.sleep(args.sleep)

    logger.info("Done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
