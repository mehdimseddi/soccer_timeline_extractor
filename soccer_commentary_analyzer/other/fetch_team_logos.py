# other/fetch_team_logos.py
from __future__ import annotations
import os
import re
import json
import time
import argparse
import sqlite3
from typing import Optional, Tuple, Dict, Any, List
from urllib.parse import urlparse, quote

import requests
from bs4 import BeautifulSoup

try:
    # Load package config when executed as module
    from ..config import DATABASE_PATH, OUTPUT_DIR, logger
except Exception:
    # Fallbacks for standalone script execution
    import logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("fetch_team_logos")
    DATABASE_PATH = os.environ.get("DATABASE_PATH", os.path.join(os.path.dirname(__file__), "..", "database", "teams_players.db"))
    OUTPUT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "output"))

WIKI_API = "https://ar.wikipedia.org/w/api.php"
WIKIDATA_API = "https://www.wikidata.org/w/api.php"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
WD_SPARQL = "https://query.wikidata.org/sparql"
USER_AGENT = "soccer_commentary_analyzer/1.0 (contact: anonymous@example.com)"

LOGO_DIR = os.path.join(OUTPUT_DIR, "team_logos")
MANIFEST_PATH = os.path.join(LOGO_DIR, "manifest.json")


def _http_get(url: str, **params) -> requests.Response:
    headers = {"User-Agent": USER_AGENT}
    r = requests.get(url, params=params or None, headers=headers, timeout=20)
    r.raise_for_status()
    return r


def _http_get_raw(url: str, headers: Optional[Dict[str, str]] = None, params: Optional[Dict[str, Any]] = None) -> requests.Response:
    h = {"User-Agent": USER_AGENT}
    if headers:
        h.update(headers)
    r = requests.get(url, headers=h, params=params, timeout=25)
    r.raise_for_status()
    return r


def slugify(s: str) -> str:
    s = re.sub(r"[^\w\-\u0600-\u06FF]+", "_", s, flags=re.U)
    return re.sub(r"_+", "_", s).strip("_")


def ensure_dirs():
    os.makedirs(LOGO_DIR, exist_ok=True)


def load_manifest() -> Dict[str, Any]:
    ensure_dirs()
    if os.path.exists(MANIFEST_PATH):
        try:
            with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_manifest(manifest: Dict[str, Any]) -> None:
    ensure_dirs()
    tmp_path = MANIFEST_PATH + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, MANIFEST_PATH)


def wiki_search_ar(title: str) -> Optional[str]:
    """Return top Arabic Wikipedia page title for a team name."""
    try:
        r = _http_get(WIKI_API, action="query", list="search", srsearch=title, srlimit=1, format="json")
        hits = r.json().get("query", {}).get("search", [])
        if hits:
            return hits[0].get("title")
    except Exception as e:
        logger.debug(f"wiki_search_ar error: {e}")
    return None


def get_wikidata_qid_from_ar_wikipedia(title: str) -> Optional[str]:
    try:
        r = _http_get(WIKI_API, action="query", prop="pageprops", titles=title, ppprop="wikibase_item", format="json")
        pages = r.json().get("query", {}).get("pages", {})
        for _, p in pages.items():
            qid = p.get("pageprops", {}).get("wikibase_item")
            if qid:
                return qid
    except Exception as e:
        logger.debug(f"get_wikidata_qid_from_ar_wikipedia error: {e}")
    return None


def _wikidata_claims(qid: str) -> Dict[str, Any]:
    r = _http_get(WIKIDATA_API, action="wbgetentities", ids=qid, props="claims", format="json")
    return r.json().get("entities", {}).get(qid, {}).get("claims", {})


def get_commons_filenames_from_wikidata(qid: str) -> Dict[str, Optional[str]]:
    """Return candidate filenames from Wikidata: prefer P154 (logo), fallback P18 (image)."""
    try:
        claims = _wikidata_claims(qid)
        def _one(prop: str) -> Optional[str]:
            c = claims.get(prop)
            if not c:
                return None
            try:
                return c[0]["mainsnak"]["datavalue"]["value"]
            except Exception:
                return None
        return {"logo": _one("P154"), "image": _one("P18")}
    except Exception as e:
        logger.debug(f"get_commons_filenames_from_wikidata error: {e}")
        return {"logo": None, "image": None}


def is_football_club(qid: str) -> bool:
    """Light guard: ensure entity is a football club via P31."""
    try:
        claims = _wikidata_claims(qid)
        p31 = claims.get("P31", [])
        ids = set()
        for c in p31:
            try:
                ids.add(c["mainsnak"]["datavalue"]["value"]["id"])  # e.g., Q476028
            except Exception:
                continue
        return any(x in ids for x in {"Q476028", "Q847017", "Q12973014"})
    except Exception:
        return False


def sparql_p154_preferred(qid: str) -> List[str]:
    """Use Wikidata SPARQL to get preferred-rank P154 (logo image). Return filenames (prefer SVG)."""
    try:
        query = f"""
        SELECT ?file WHERE {{
          VALUES ?club {{ wd:{qid} }}
          ?club p:P154 ?stmt .
          ?stmt wikibase:rank wikibase:PreferredRank .
          ?stmt ps:P154 ?file .
        }}
        """
        r = _http_get_raw(WD_SPARQL, headers={"Accept": "application/sparql-results+json"}, params={"query": query})
        rows = r.json().get("results", {}).get("bindings", [])
        files = [row["file"]["value"].split("/")[-1] for row in rows]
        # prefer SVG
        svg = [f for f in files if f.lower().endswith(".svg")]
        return svg or files
    except Exception:
        return []


BAD_TITLE_WORDS = ("kit", "jersey", "maillot", "stadium", "player", "fans")
GOOD_TITLE_WORDS = ("logo", "crest", "badge", "شعار")


def get_thumbnail_url_from_commons(filename: str, width: int = 256) -> Optional[str]:
    try:
        r = _http_get(COMMONS_API,
                      action="query",
                      prop="imageinfo",
                      titles=f"File:{filename}",
                      iiprop="url|extmetadata",
                      iiurlwidth=str(width),
                      format="json")
        pages = r.json().get("query", {}).get("pages", {})
        for _, p in pages.items():
            info = p.get("imageinfo", [])
            if info:
                thumb = info[0].get("thumburl") or info[0].get("url")
                meta = info[0].get("extmetadata", {})
                title = (meta.get("ObjectName", {}).get("value") or filename).lower()
                cats = (meta.get("Categories", {}).get("value") or "").lower()
                # Heuristics: prefer likely logos, avoid kits/players/stadiums
                if any(g in title for g in GOOD_TITLE_WORDS) or "logo" in cats or "crest" in cats:
                    if not any(b in title for b in BAD_TITLE_WORDS):
                        return thumb
                # Fallback: still return thumb if nothing better is available
                return thumb
    except Exception as e:
        logger.debug(f"get_thumbnail_url_from_commons error: {e}")
    return None


def commons_sdc_depicts(filename: str) -> List[str]:
    """Fetch SDC 'depicts' labels for a Commons file via Special:EntityData."""
    try:
        url = f"https://commons.wikimedia.org/wiki/Special:EntityData/File:{quote(filename)}.json"
        r = _http_get_raw(url, headers={"Accept": "application/json"})
        entities = r.json().get("entities", {})
        # Entity id like M123456
        for _, ent in entities.items():
            stmts = ent.get("statements", {})
            p180 = stmts.get("P180", [])  # depicts
            labels: List[str] = []
            for st in p180:
                try:
                    qid = st["mainsnak"]["datavalue"]["value"]["id"]
                    # resolve label via Wikidata API (could cache)
                    rr = _http_get(WIKIDATA_API, action="wbgetentities", ids=qid, props="labels", languages="en|ar", format="json")
                    ent2 = rr.json().get("entities", {}).get(qid, {})
                    lb = ent2.get("labels", {})
                    labels.append(lb.get("en", {}).get("value") or lb.get("ar", {}).get("value") or "")
                except Exception:
                    continue
            return [l for l in labels if l]
    except Exception:
        return []
    return []


def download(url: str, dest_path: str) -> str:
    ensure_dirs()
    with _http_get(url) as r:
        with open(dest_path, "wb") as f:
            for chunk in r.iter_content(8192):
                if chunk:
                    f.write(chunk)
    return dest_path


def parse_infobox_logo_from_ar_wikipedia(title: str) -> Optional[str]:
    """Fallback: parse infobox logo image URL from Arabic Wikipedia page."""
    try:
        # Get HTML content
        r = _http_get(f"https://ar.wikipedia.org/wiki/{title}")
        soup = BeautifulSoup(r.text, "html.parser")
        infobox = soup.find("table", class_=re.compile("infobox"))
        if not infobox:
            return None
        # Prefer a row labeled شعار/Logo
        for row in infobox.select("tr"):
            th = row.find("th")
            if not th:
                continue
            label = (th.get_text(strip=True) or "").strip()
            if any(k in label for k in ("شعار", "الشعار", "Logo")):
                img = row.find("img")
                if img:
                    src = img.get("src") or img.get("data-src") or ""
                    if src:
                        return ("https:" + src) if src.startswith("//") else src
        # Fallback: first image
        img = infobox.find("img")
        if not img:
            return None
        src = img.get("src") or img.get("data-src") or ""
        return ("https:" + src) if src.startswith("//") else src
    except Exception as e:
        logger.debug(f"parse_infobox_logo_from_ar_wikipedia error: {e}")
    return None


def pick_best_from_claims(claims: Dict[str, Any]) -> Optional[str]:
    """Pick best P154 (logo) considering rank and extension preference (SVG first)."""
    p154 = claims.get("P154") or []
    if not p154:
        return None
    # Group by rank
    ranked = {"preferred": [], "normal": [], "deprecated": []}
    for stmt in p154:
        try:
            rank = stmt.get("rank", "normal")
            filename = stmt["mainsnak"]["datavalue"]["value"]
            ranked.setdefault(rank, []).append(filename)
        except Exception:
            continue
    def prefer_svg(files: List[str]) -> Optional[str]:
        if not files:
            return None
        svg = [f for f in files if str(f).lower().endswith(".svg")]
        return svg[0] if svg else files[0]
    return prefer_svg(ranked.get("preferred") or ranked.get("normal") or [])


def commons_search_logo_candidates(team_name_ar: str, limit: int = 5) -> List[str]:
    """Search Commons for 'team + logo' files (namespace File:). Return list of titles (without 'File:')."""
    try:
        q = f"{team_name_ar} logo"
        r = _http_get(COMMONS_API,
                      action="query",
                      format="json",
                      generator="search",
                      gsrlimit=str(limit),
                      gsrnamespace="6",  # File namespace
                      gsrsearch=q)
        pages = r.json().get("query", {}).get("pages", {})
        titles = []
        for _, p in pages.items():
            title = p.get("title", "")
            if title.startswith("File:"):
                titles.append(title.split(":", 1)[1])
        return titles
    except Exception as e:
        logger.debug(f"commons_search_logo_candidates error: {e}")
        return []


def optional_llm_curate(team: str, candidates: List[str], min_conf: float = 0.7) -> Optional[str]:
    """Optionally run the separate LLM curator to pick the best among URLs. Returns saved relative path or None."""
    try:
        from .logo_curator_llm import curate as _curate, Candidate as _Cand
        cands = [_Cand(url=u, source="fetcher") for u in candidates]
        best = _curate(team, cands, min_conf=min_conf)
        if best and best.get("saved_path"):
            return best["saved_path"]
    except Exception as e:
        logger.debug(f"optional_llm_curate skipped: {e}")
    return None


def fetch_team_logo(team_name_ar: str, width: int = 256) -> Tuple[Optional[str], Dict[str, Any]]:
    """
    Attempt to fetch team logo image for the Arabic team name.
    Returns (local_path, metadata)
    metadata keys: {"source": "wikidata"|"infobox", "title", "qid", "remote_url"}
    """
    ensure_dirs()
    meta: Dict[str, Any] = {"team": team_name_ar, "width": width}

    # 1) find Arabic Wikipedia title
    title = wiki_search_ar(team_name_ar) or team_name_ar
    meta["title"] = title

    # 2) Wikidata: prefer P154 (logo), else P18, with rank/ext preference and Commons filtering
    qid = get_wikidata_qid_from_ar_wikipedia(title)
    if qid:
        meta["qid"] = qid
        # Guard: ensure this QID is a football club
        if not is_football_club(qid):
            logger.debug(f"Entity {qid} not a football club; skipping P154/P18")
        else:
            # First try SPARQL preferred P154
            fns = sparql_p154_preferred(qid)
            fn = fns[0] if fns else None
            if not fn:
                claims = _wikidata_claims(qid)
                fn = pick_best_from_claims(claims)
            tried_urls: List[str] = []
            if fn:
                url = get_thumbnail_url_from_commons(fn, width=width)
                if url:
                    # Extra SDC check: depicts should include 'logo' or 'emblem' if available
                    depicts = commons_sdc_depicts(fn)
                    if depicts and not any(any(k in d.lower() for k in ("logo", "emblem", "crest", "شعار")) for d in depicts):
                        logger.debug(f"SDC depicts did not indicate logo for {fn}: {depicts}")
                    else:
                        tried_urls.append(url)
                        meta["source"] = "wikidata:P154"
                        meta["remote_url"] = url
                        ext = os.path.splitext(urlparse(url).path)[1] or ".jpg"
                        local = os.path.join(LOGO_DIR, f"{slugify(team_name_ar)}_{width}{ext}")
                        try:
                            download(url, local)
                            return local, meta
                        except Exception as e:
                            logger.warning(f"Download failed from Commons: {e}")
            # try P18 if no P154 success
            files = get_commons_filenames_from_wikidata(qid)
            if files.get("image"):
                url = get_thumbnail_url_from_commons(files["image"], width=width)
                if url:
                    tried_urls.append(url)
                    meta["source"] = "wikidata:P18"
                    meta["remote_url"] = url
                    ext = os.path.splitext(urlparse(url).path)[1] or ".jpg"
                    local = os.path.join(LOGO_DIR, f"{slugify(team_name_ar)}_{width}{ext}")
                    try:
                        download(url, local)
                        return local, meta
                    except Exception as e:
                        logger.warning(f"Download failed from Commons: {e}")
            # Try Commons search for 'team + logo'
            for title_fn in commons_search_logo_candidates(team_name_ar, limit=6):
                url = get_thumbnail_url_from_commons(title_fn, width=width)
                if not url:
                    continue
                tried_urls.append(url)
                # Optionally LLM-curate among multiple candidates when available
                curated_rel = optional_llm_curate(team_name_ar, tried_urls, min_conf=0.75)
                if curated_rel:
                    meta["source"] = "curated"
                    meta["remote_url"] = ""
                    return os.path.join(OUTPUT_DIR, curated_rel), meta
                # If no curator, use first acceptable
                meta["source"] = "commons:search"
                meta["remote_url"] = url
                ext = os.path.splitext(urlparse(url).path)[1] or ".jpg"
                local = os.path.join(LOGO_DIR, f"{slugify(team_name_ar)}_{width}{ext}")
                try:
                    download(url, local)
                    return local, meta
                except Exception:
                    continue

    # 3) Fallback: infobox image on Arabic Wikipedia
    try:
        infobox_url = parse_infobox_logo_from_ar_wikipedia(title)
        if infobox_url:
            meta["source"] = "infobox"
            meta["remote_url"] = infobox_url
            ext = os.path.splitext(urlparse(infobox_url).path)[1] or ".jpg"
            local = os.path.join(LOGO_DIR, f"{slugify(team_name_ar)}_{width}{ext}")
            download(infobox_url, local)
            return local, meta
    except Exception as e:
        logger.warning(f"Infobox fallback failed: {e}")

    return None, meta


def list_db_teams(db_path: str) -> List[str]:
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT name FROM Team ORDER BY name ASC")
        return [r[0] for r in cur.fetchall()]
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Fetch team logos via Wikidata/Wikipedia")
    parser.add_argument("--teams", nargs="*", default=None, help="One or more Arabic team names to fetch")
    parser.add_argument("--all-db", action="store_true", help="Fetch for all teams in the DB Team table")
    parser.add_argument("--db", default=DATABASE_PATH, help="Path to SQLite DB (default: from config)")
    parser.add_argument("--width", type=int, default=256, help="Thumbnail width (default: 256)")
    parser.add_argument("--sleep", type=float, default=0.5, help="Sleep between requests seconds (default: 0.5)")

    args = parser.parse_args()

    if not args.teams and not args.all_db:
        parser.error("Provide --teams names or --all-db")

    if args.all_db:
        teams = list_db_teams(args.db)
        if not teams:
            logger.error("No teams found in DB")
            return 2
    else:
        teams = args.teams or []

    manifest = load_manifest()
    results = []

    for name in teams:
        try:
            local_path, meta = fetch_team_logo(name, width=args.width)
            entry = manifest.get(name, {})
            if local_path:
                logger.info(f"Logo: {name} -> {local_path}")
                entry.update({
                    "path": os.path.relpath(local_path, OUTPUT_DIR),
                    "width": args.width,
                    "source": meta.get("source"),
                    "remote_url": meta.get("remote_url"),
                    "qid": meta.get("qid"),
                    "title": meta.get("title"),
                    "last_fetch_ts": int(time.time())
                })
                manifest[name] = entry
                results.append((name, local_path))
            else:
                logger.warning(f"No logo found for: {name}")
        except Exception as e:
            logger.warning(f"Failed to fetch logo for {name}: {e}")
        time.sleep(args.sleep)

    save_manifest(manifest)

    # Also dump a simple CSV index for convenience
    try:
        idx_path = os.path.join(LOGO_DIR, "index.csv")
        with open(idx_path, "w", encoding="utf-8") as f:
            f.write("team,path,source,remote_url,qid\n")
            for team, info in manifest.items():
                f.write(
                    f"{team},{info.get('path','')},{info.get('source','')},{info.get('remote_url','')},{info.get('qid','')}\n"
                )
        logger.info(f"Index written: {idx_path}")
    except Exception:
        pass

    logger.info(f"Done. Logos fetched: {len(results)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
