from typing import Dict, List, Tuple
from collections import defaultdict, Counter
from rapidfuzz import fuzz

from ..state_type.types_utils import CommentaryState
from ..models.schemas import PlayerInfo
from ..utils.arabic import normalize_arabic_text
from ..config import logger
from ..utils.metrics import metrics


def _normalized_name(name: str) -> str:
    if not name:
        return ""
    # Arabic normalization + lowercase + collapse spaces
    base = normalize_arabic_text(name)
    return " ".join(base.lower().split())


def _merge_players(candidates: List[PlayerInfo]) -> PlayerInfo:
    # Deterministic merge: prefer canonical-like (longer name), then with number, then specific position
    if not candidates:
        raise ValueError("No candidates to merge")
    # Sort by: has number desc, position specificity desc, name length desc
    def pos_score(p: PlayerInfo) -> int:
        if not p.position or p.position == "unknown":
            return 0
        if p.position == "goalkeeper":
            return 3
        # generic non-unknown position
        return 2

    ranked = sorted(
        candidates,
        key=lambda p: (
            1 if (p.number and str(p.number).strip()) else 0,
            pos_score(p),
            len(p.name or ""),
        ),
        reverse=True,
    )
    winner = ranked[0]

    # Merge best attributes from others if missing
    numbers = [p.number for p in candidates if p.number]
    if not winner.number and numbers:
        # Most common number
        winner.number = Counter(numbers).most_common(1)[0][0]

    if (not winner.position or winner.position == "unknown"):
        for p in ranked[1:]:
            if p.position and p.position != "unknown":
                winner.position = p.position
                break

    return winner


def deduplicate_players_node(state: CommentaryState) -> CommentaryState:
    players: List[PlayerInfo] = state.get("extracted_players", [])
    if not players:
        return state

    # Separate by team; never merge across teams unless exact canonical names match
    team_to_players: Dict[str, List[PlayerInfo]] = defaultdict(list)
    unassigned: List[PlayerInfo] = []
    for p in players:
        (team_to_players[p.team].append(p) if p.team else unassigned.append(p))

    deduped: List[PlayerInfo] = []
    # Metrics accumulators
    total_exact_merges = 0
    total_fuzzy_merges = 0
    total_number_conflicts = 0
    total_ambiguous_merges = 0

    def dedup_within_bucket(bucket: List[PlayerInfo]) -> Tuple[List[PlayerInfo], Dict[str, int]]:
        if not bucket:
            return [], {"exact": 0, "fuzzy": 0, "num_conflicts": 0, "ambiguous": 0}
        # First pass: exact normalized-name match
        clusters: Dict[str, List[PlayerInfo]] = defaultdict(list)
        for p in bucket:
            key = _normalized_name(p.name)
            clusters[key].append(p)
        exact_merges = sum(len(g) - 1 for g in clusters.values() if len(g) > 1)

        # Second pass: fuzzy merge on close normalized names considering jersey number as a boost/guard
        keys = list(clusters.keys())
        merged_map: Dict[str, str] = {k: k for k in keys}
        fuzzy_merges = 0
        number_conflicts = 0
        ambiguous_merges = 0
        for i, ki in enumerate(keys):
            for kj in keys[i+1:]:
                if merged_map[ki] != ki or merged_map[kj] != kj:
                    continue
                score = fuzz.token_set_ratio(ki, kj)
                if score >= 92:
                    # Check for jersey number conflicts; if strong conflict, avoid merging
                    nums_i = {p.number for p in clusters[ki] if p.number}
                    nums_j = {p.number for p in clusters[kj] if p.number}
                    if nums_i and nums_j and nums_i.isdisjoint(nums_j):
                        # Conflicting numbers → skip merge
                        number_conflicts += 1
                        continue
                    if not nums_i and not nums_j:
                        ambiguous_merges += 1
                    # Merge kj into ki
                    merged_map[kj] = ki
                    fuzzy_merges += 1

        # Build final groups
        final_groups: Dict[str, List[PlayerInfo]] = defaultdict(list)
        for k, group in clusters.items():
            final_groups[merged_map[k]].extend(group)

        # Reduce each group
        results: List[PlayerInfo] = []
        for _, group in final_groups.items():
            winner = _merge_players(group)
            results.append(winner)
        return results, {
            "exact": exact_merges,
            "fuzzy": fuzzy_merges,
            "num_conflicts": number_conflicts,
            "ambiguous": ambiguous_merges,
        }

    # Dedup per team
    for team, bucket in team_to_players.items():
        try:
            logger.info("Player dedup team '%s': %d candidates", team or "(unassigned)", len(bucket))
        except Exception:
            pass
        results, stats = dedup_within_bucket(bucket)
        deduped.extend(results)
        total_exact_merges += stats["exact"]
        total_fuzzy_merges += stats["fuzzy"]
        total_number_conflicts += stats["num_conflicts"]
        total_ambiguous_merges += stats["ambiguous"]
        try:
            logger.info("Player dedup team '%s': %d→%d", team or "(unassigned)", len(bucket), len(results))
        except Exception:
            pass

    # Handle unassigned players as a separate bucket (riskier merges):
    results, stats = dedup_within_bucket(unassigned)
    deduped.extend(results)
    total_exact_merges += stats["exact"]
    total_fuzzy_merges += stats["fuzzy"]
    total_number_conflicts += stats["num_conflicts"]
    total_ambiguous_merges += stats["ambiguous"]

    # Final guard: unique by (normalized name, team)
    seen: set[Tuple[str, str]] = set()
    unique: List[PlayerInfo] = []
    for p in deduped:
        key = (_normalized_name(p.name), p.team or "")
        if key not in seen:
            seen.add(key)
            unique.append(p)
        else:
            logger.warning(f"Duplicate after dedup pass removed: {p.name} ({p.team})")

    logger.info(f"Player dedup: {len(players)} → {len(unique)}")
    # Emit metrics
    try:
        metrics.emit("player_dedup_summary", {
            "total_input": len(players),
            "total_output": len(unique),
            "duplicates_merged": max(0, len(players) - len(unique)),
            "merges_by_strategy": {
                "exact_normalized": total_exact_merges,
                "fuzzy": total_fuzzy_merges,
            },
            "number_conflicts": total_number_conflicts,
            "ambiguous_merges": total_ambiguous_merges,
        })
    except Exception:
        pass
    return {**state, "extracted_players": unique}
