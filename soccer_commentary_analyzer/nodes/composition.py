from ..models.schemas import PlayerInfo
from ..state_type.types_utils import CommentaryState
from ..config import logger
from ..utils.arabic import normalize_arabic_text

def enforce_valid_team_composition(state: CommentaryState) -> CommentaryState:
    """
    Combined enforcement of:
    - Exactly 11 players per team
    - Valid positional composition (1 GK, min defenders/midfielders/attackers)
    - NO duplicate players
    """
    from collections import defaultdict

    extracted_players = state["extracted_players"]
    if not extracted_players:
        return state
    
    # Assume earlier pipeline performed deduplication. Keep a stronger safety net (normalized keys).
    seen = set()
    unique_players = []
    for p in extracted_players:
        norm_name = " ".join(normalize_arabic_text((p.name or "")).lower().split())
        norm_team = (p.team or "").strip()
        key = (norm_name, norm_team)
        if key in seen:
            logger.warning(f"Duplicate detected in composition stage: {p.name} ({p.team}) — skipping re-add")
            continue
        seen.add(key)
        unique_players.append(p)
    extracted_players = unique_players

    # Group by team
    team_players = defaultdict(list)
    unassigned_players = []

    for player in extracted_players:
        if player.team:
            team_players[player.team].append(player)
        else:
            unassigned_players.append(player)

    final_players = []

    for team, players in team_players.items():
        logger.info(f"Enforcing valid composition for team: {team}")

        # Classify players by position
        goalkeepers = [p for p in players if p.position == "goalkeeper"]
        defenders = [p for p in players if p.position and ("back" in p.position or "defensive" in p.position)]
        midfielders = [p for p in players if p.position and "midfielder" in p.position and p not in defenders]
        attackers = [p for p in players if p.position and ("winger" in p.position or "striker" in p.position or "attacking" in p.position)]
        unknown = [p for p in players if not p.position or p.position == "unknown"]

        # --- Step 1: Ensure exactly 1 goalkeeper ---
        gk_promoted = False
        if not goalkeepers:
            logger.warning("No goalkeeper found. Trying to promote a defender...")
            candidate = next((p for p in defenders), None)
            if not candidate:
                candidate = next((p for p in midfielders), None)
            if candidate:
                candidate.position = "goalkeeper"
                goalkeepers = [candidate]
                if candidate in defenders: defenders.remove(candidate)
                logger.info(f"Promoted {candidate.name} to goalkeeper.")
                gk_promoted = True
            else:
                logger.error("No valid fallback. Adding unknown goalkeeper.")
                placeholder = PlayerInfo(
                    name="حارس مرمى غير معروف",
                    team=team,
                    number=None,
                    position="goalkeeper"
                )
                goalkeepers = [placeholder]
        else:
            keeper = goalkeepers[0]
            logger.info(f"Keeper confirmed: {keeper.name}")
            unknown.extend(goalkeepers[1:])  # ex-GKs become unknown

        # --- Step 2: Ensure at least one in each group ---
        if not defenders:
            logger.warning("No defenders → promoting first midfielder")
            fallback = midfielders.pop(0) if midfielders else unknown.pop(0) if unknown else None
            if fallback:
                fallback.position = "center_back"
                defenders.append(fallback)
        if not midfielders:
            logger.warning("No midfielders → promoting defender or attacker")
            fallback = defenders.pop(0) if defenders else attackers.pop(0) if attackers else unknown.pop(0) if unknown else None
            if fallback:
                fallback.position = "central_midfielder"
                midfielders.append(fallback)
        if not attackers:
            logger.warning("No attackers → promoting midfielder")
            fallback = midfielders.pop(0) if midfielders else defenders.pop(0) if defenders else unknown.pop(0) if unknown else None
            if fallback:
                fallback.position = "striker"
                attackers.append(fallback)

        # --- Step 3: Build final 11 ---
        selected = goalkeepers[:1]
        remaining_slots = 10

        def_slots = min(5, max(3, remaining_slots // 3 + 1))
        mid_slots = min(5, max(3, remaining_slots // 3))
        att_slots = remaining_slots - def_slots - mid_slots

        def_slots = min(def_slots, len(defenders))
        mid_slots = min(mid_slots, len(midfielders))
        att_slots = min(att_slots, len(attackers))

        # Add players to selected
        selected.extend(defenders[:def_slots])
        selected.extend(midfielders[:mid_slots])
        selected.extend(attackers[:att_slots])
        remaining_slots -= (def_slots + mid_slots + att_slots)

        # Build remaining pool from leftovers
        remaining_pool = (
            defenders[def_slots:] +
            midfielders[mid_slots:] +
            attackers[att_slots:] +
            unknown
        )

        # Sort by original order (earlier mentioned = higher priority)
        remaining_pool = sorted(remaining_pool, key=lambda p: players.index(p))

        # === FIX 2: Avoid re-adding players already in selected ===
        already_selected = set((p.name, p.team) for p in selected)
        remaining_pool = [p for p in remaining_pool if (p.name, p.team) not in already_selected]

        selected.extend(remaining_pool[:remaining_slots])

        # Log dropped players
        selected_set = {(p.name, p.team) for p in selected}
        dropped = [p for p in players if (p.name, p.team) not in selected_set]
        for p in dropped:
            logger.info(f"Dropped from {team}: {p.name} ({p.position})")

        final_players.extend(selected)
        logger.info(f"Final {team}: {len(selected)} players with valid composition. gk_promoted={gk_promoted}")

    # Handle unassigned
    if unassigned_players:
        logger.warning(f"{len(unassigned_players)} players ignored (no team): {[p.name for p in unassigned_players]}")

    return {**state, "extracted_players": final_players}