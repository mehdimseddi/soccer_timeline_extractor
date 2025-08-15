// types/match.ts
export type PlayerPosition =
    | "goalkeeper"
    | "center_back"
    | "right_back"
    | "left_back"
    | "defensive_midfielder"
    | "central_midfielder"
    | "attacking_midfielder"
    | "right_winger"
    | "left_winger"
    | "striker"
    | "second_striker";

export type EventType =
    | "goal"
    | "yellow_card"
    | "yellow_red"
    | "red_card"
    | "substitution"
    | "penalty"
    | "half"
    | "full";

export interface Player {
    name: string;
    team: string;
    position?: PlayerPosition | null;
    number?: number | null;
}

export interface MatchEvent {
    type: EventType;
    label?: string | null;
    player?: string | null;
    player_in?: string | null;
    player_out?: string | null;
    team?: string | null;
    time: string;
    details?: string | null;
    score?: string | null;
}

export interface MatchInfo {
    match_id: string;
    home_team: string;
    away_team: string;
    date?: string | null;
    venue?: string | null;
    referee?: string | null;
}

export interface AnalysisData {
    events?: MatchEvent[];
    players?: Player[];
}

export interface MatchResultResponse {
    match_id: string;
    home_team: string;
    away_team: string;
    score: {
        home: number;
        away: number;
    };
    events_count: number;
    players_count: number;
    excel_report: string;
    events_csv: string;
    players_csv: string;
    analysis: AnalysisData;
    // Optional artifacts and transcript for richer UI
    artifacts?: {
        excel?: string;
        events_csv?: string;
        players_csv?: string;
        vtt?: string;
        media_url?: string;
    };
    // Optional team logos (backend expansion via ?expand=logos)
    home_team_logo_url?: string;
    away_team_logo_url?: string;
    transcript_cues?: Array<{
        start_ms: number;
        end_ms: number;
        text: string;
    }>;
}


export type Team = {
    name: string;
    id?: number;
    href?: string;
    logo?: string; // will use placeholder or dynamic
};

// Raw JSON structure
export type RawMatchData = {
    match_id: string;
    home_team: string;
    away_team: string;
    score: Record<string, number>;
    analysis: {
        events: Array<{
            type: "goal" | "yellow_card";
            player: string;
            team: string;
            time: string;
            details: string;
            confidence: number;
        }>;
        players: Array<{
            name: string;
            team: string;
            position: string;
        }>;
    };
};