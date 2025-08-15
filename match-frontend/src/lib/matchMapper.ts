// src/lib/matchMapper.ts
import type { MatchEvent, MatchResultResponse } from "@/types/match";
import { logger } from "@/lib/logger";

export const mapRawToMatchEvents = (
    rawData: MatchResultResponse
): {
    finalScore: string;
    events: MatchEvent[];
} => {
    logger.debug("Mapping raw data to match events:", rawData);
    const { home_team, analysis } = rawData;
    const { events: rawEvents } = analysis;

    const MINUTE_MS = 60_000;
    // const HALF_TIME_MS = 45 * MINUTE_MS;

    const parseClockToMs = (clock: string | undefined | null): number => {
        if (!clock) return 0;
        const s = String(clock).replace(/[\s'”‘’`]/g, "");
        const m = /^(\d+)(?:\+(\d+))?$/.exec(s);
        if (m) {
            const baseMin = Number(m[1] || 0);
            const addedMin = Number(m[2] || 0);
            return (baseMin + addedMin) * MINUTE_MS;
        }
        const n = Number.parseInt(s, 10);
        return Number.isFinite(n) ? n * MINUTE_MS : 0;
    };

    // Safe extraction with defaults
    const eventsRaw: MatchEvent[] = Array.isArray(rawEvents)
        ? rawEvents
            .filter((e): e is MatchEvent => e !== null && typeof e === "object")
            .map((e): MatchEvent => ({
                ...e,
                player: e.player || null,
                player_in: e.player_in || null,
                player_out: e.player_out || null,
                team: e.team || null,
                time: e.time || "?",
                details: e.details || "",
            }))
        : [];

    // Merge yellow + red shown to the same player at the same minute+added into a single yellow_red
    const events: MatchEvent[] = (() => {
        const toRemove = new Set<number>();
        const indexByKey: Record<string, number[]> = {};
        const makeKey = (ev: MatchEvent): string => {
            const tMs = parseClockToMs(ev.time);
            const playerKey = ev.player || "";
            const teamKey = ev.team || "";
            return `${tMs}|${teamKey}|${playerKey}`;
        };
        eventsRaw.forEach((ev, idx) => {
            if (!ev.player || !ev.team) return; // only merge when player and team are known
            const key = makeKey(ev);
            (indexByKey[key] ||= []).push(idx);
        });
        Object.values(indexByKey).forEach((indices) => {
            const types = indices.map(i => eventsRaw[i].type);
            const hasYellow = types.includes("yellow_card");
            const hasRed = types.includes("red_card");
            if (hasYellow && hasRed) {
                // Find the red card event; repurpose it into yellow_red and drop yellow
                const redIndex = indices.find(i => eventsRaw[i].type === "red_card");
                if (redIndex !== undefined) {
                    eventsRaw[redIndex] = { ...eventsRaw[redIndex], type: "yellow_red", label: eventsRaw[redIndex].label || "Second yellow → Red" };
                }
                indices.forEach(i => { if (eventsRaw[i].type === "yellow_card") toRemove.add(i); });
            }
        });
        return eventsRaw.filter((_, idx) => !toRemove.has(idx));
    })();

    // Initialize score tracking and build a single ordered list.
    let homeScore = 0;
    let awayScore = 0;
    const output: MatchEvent[] = [];

    // Enrich with parsed components
    const enriched = events.map((ev, idx) => {
        const s = String(ev.time).replace(/[\s'”‘’`]/g, "");
        const m = /^(\d+)(?:\+(\d+))?$/.exec(s);
        const baseMin = m ? Number(m[1] || 0) : Number.parseInt(s, 10) || 0;
        const addedMin = m ? Number(m[2] || 0) : 0;
        return { ev, idx, t: (baseMin + addedMin) * MINUTE_MS, baseMin, addedMin };
    });
    enriched.sort((a, b) => (a.t - b.t) || (a.idx - b.idx));

    let insertedHT = false;
    let insertedFT = false;
    const hadFirstHalf = enriched.some(x => x.baseMin <= 45);

    const push = (e: MatchEvent) => output.push(e);

    const pushWith = (type: MatchEvent["type"], base: Partial<MatchEvent> & { time: string }) => {
        push({
            type,
            time: base.time,
            label: base.label ?? null,
            score: base.score,
            player: base.player ?? null,
            player_in: base.player_in ?? null,
            player_out: base.player_out ?? null,
            team: base.team,
            details: base.details ?? "",
        } as MatchEvent);
    };

    for (const { ev, baseMin } of enriched) {
        // Insert HT right before the first event whose base minute exceeds 45
        if (!insertedHT && hadFirstHalf && baseMin > 45) {
            pushWith("half", { time: "45'", label: "HT", score: `${homeScore} - ${awayScore}` });
            insertedHT = true;
        }
        // Insert FT right before the first event whose base minute exceeds 90
        if (!insertedFT && baseMin > 90) {
            const finalScoreBeforeFT = `${homeScore} - ${awayScore}`;
            pushWith("full", { time: "90'", label: "FT", score: finalScoreBeforeFT });
            insertedFT = true;
        }

        const isHome = ev.team === home_team;
        const team: "home" | "away" = isHome ? "home" : "away";
        const timeStr = `${ev.time}'`;

        if (ev.type === "goal") {
            if (isHome) homeScore++; else awayScore++;
            pushWith("goal", { time: timeStr, player: ev.player ?? null, team, score: `${homeScore} - ${awayScore}` });
        } else if (ev.type === "yellow_card") {
            pushWith("yellow_card", { time: timeStr, player: ev.player ?? null, team });
        } else if (ev.type === "red_card") {
            pushWith("red_card", { time: timeStr, player: ev.player ?? null, team });
        } else if (ev.type === "yellow_red") {
            pushWith("yellow_red", { time: timeStr, player: ev.player ?? null, team });
        } else if (ev.type === "substitution") {
            pushWith("substitution", { time: timeStr, team, player_in: ev.player_in ?? null, player_out: ev.player_out ?? null });
        } else if (ev.type === "penalty") {
            pushWith("penalty", { time: timeStr, player: ev.player ?? null, team, score: ev.score });
        }
    }

    // If we had first-half events but never inserted HT (e.g., only first-half data), add it now
    if (hadFirstHalf && !insertedHT) {
        pushWith("half", { time: "45'", label: "HT", score: `${homeScore} - ${awayScore}` });
        insertedHT = true;
    }

    const finalScore = `${homeScore} - ${awayScore}`;
    if (!insertedFT) {
        pushWith("full", { time: "90'", label: "FT", score: finalScore });
    }

    logger.debug("Sorted events:", output);
    return { finalScore, events: output };
};