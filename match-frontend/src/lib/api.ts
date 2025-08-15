// src/lib/api.ts
import type { MatchResultResponse } from "@/types/match";
import { http } from "@/lib/http";
import { logger } from "@/lib/logger";

export interface AnalyzeInput {
    commentary: string;
    home_team_id?: number;
    away_team_id?: number;
}

export interface ApiError {
    detail: string;
}


export const analyzeCommentary = async (
    input: AnalyzeInput
): Promise<MatchResultResponse> => {
    // Ask backend to include logo URLs when available
    const data = await http<MatchResultResponse>({
        path: "/analyze?expand=logos",
        method: "POST",
        body: input,
    });

    // Fallback defaults if backend returns incomplete data
    return {
        ...data,
        score: data.score ?? { home: 0, away: 0 },
        analysis: {
            events: data.analysis?.events ?? [],
            players: data.analysis?.players ?? []
        },
    };
};

export const analyzeMedia = async (
    file: File
    ,
    opts?: { home_team_id?: number; away_team_id?: number }
): Promise<MatchResultResponse> => {
    const formData = new FormData();
    formData.append('file', file);
    if (opts?.home_team_id != null) formData.append('home_team_id', String(opts.home_team_id));
    if (opts?.away_team_id != null) formData.append('away_team_id', String(opts.away_team_id));

    return await http<MatchResultResponse>({
        path: "/analyze-media/?expand=logos",
        method: "POST",
        asFormData: true,
        // body typed as unknown to keep http generic
        body: formData as unknown as BodyInit,
    });
};

export const analyzeYoutube = async (
    youtube_url: string,
    opts?: { home_team_id?: number; away_team_id?: number }
): Promise<MatchResultResponse> => {
    // Create FormData object
    const formData = new FormData();
    formData.append("url", youtube_url); // must match backend parameter name

    if (opts?.home_team_id != null) {
        formData.append("home_team_id", String(opts.home_team_id));
    }
    if (opts?.away_team_id != null) {
        formData.append("away_team_id", String(opts.away_team_id));
    }

    // Send request
    const data = await http<MatchResultResponse>({
        path: "/analyze-youtube?expand=logos",
        method: "POST",
        asFormData: true,
        body: formData as unknown as BodyInit,
    });

    return {
        ...data,
        score: data.score ?? { home: 0, away: 0 },
        analysis: {
            events: data.analysis?.events ?? [],
            players: data.analysis?.players ?? [],
        },
    };
};


export const listTeams = async (): Promise<{ id: number; name: string }[]> => {
    const res = await http<unknown>({ path: "/teams", method: "GET" });
    const pickArray = (obj: unknown): unknown[] => {
        if (Array.isArray(obj)) return obj;
        if (obj && typeof obj === "object") {
            const anyObj = obj as Record<string, unknown>;
            for (const key of ["teams", "data", "items", "results"]) {
                if (Array.isArray(anyObj[key])) return anyObj[key] as unknown[];
            }
        }
        return [];
    };
    const arr = pickArray(res);
    if (!arr.length) {
        logger.warn("Teams response not an array; response=", res);
        return [];
    }
    // Normalize to minimal shape { id, name }
    const normalized = arr
        .map((raw) => {
            if (!raw || typeof raw !== "object") return null;
            const r = raw as Record<string, unknown>;
            const idSource = r.id ?? r.team_id ?? r.pk;
            const id = typeof idSource === "number" ? idSource : Number(idSource);
            const name = (r.name || r.team_name || r.display_name || r.title) as string | undefined;
            if (!id || !name) return null;
            return { id, name };
        })
        .filter((t): t is { id: number; name: string } => !!t);

    if (!normalized.length) {
        logger.warn("No valid teams after normalization; response=", res);
        return [];
    }
    return normalized;
};