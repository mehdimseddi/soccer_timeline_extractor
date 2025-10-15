// src/pages/MatchHistoryDetail.tsx
import { useEffect, useMemo, useState } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { ArrowLeft } from "lucide-react";
import { http } from "@/lib/http";
import { API_PREFIX, API_BASE_URL } from "@/lib/config";
import type { MatchResultResponse } from "@/types/match";
import MatchTimeline from "@/components/MatchTimeline";
import TeamLineup from "@/components/TeamLineup";
import MediaTranscriptView, { type MediaSource } from "@/components/MediaTranscriptView";
import { mapRawToMatchEvents } from "@/lib/matchMapper";
import type { TranscriptCue } from "@/types/transcript";
import { toast } from "sonner";

export default function MatchHistoryDetail() {
    const { matchId } = useParams<{ matchId: string }>();
    const [data, setData] = useState<MatchResultResponse | null>(null);
    const [loading, setLoading] = useState(true);
    const navigate = useNavigate();

    useEffect(() => {
        if (!matchId) return;
        const fetchMatch = async () => {
            try {
                const res = await http<any>({
                    path: `/history/${matchId}`,
                    method: "GET",
                });

                // Transform backend response to MatchResultResponse shape
                const transformed: MatchResultResponse = {
                    match_id: res.match_id,
                    home_team: res.home_team,
                    away_team: res.away_team,
                    score: res.score,
                    events_count: res.events?.length || 0,
                    players_count: res.players?.length || 0,
                    excel_report: "",
                    events_csv: "",
                    players_csv: "",
                    analysis: {
                        events: res.events || [],
                        players: res.players || [],
                    },
                    artifacts: {
                        excel: res.artifacts.excel,
                        events_csv: res.artifacts.events_csv,
                        players_csv: res.artifacts.players_csv,
                        vtt: res.artifacts.vtt,
                        media_url: res.artifacts.commentary_txt
                            ? `${API_BASE_URL}${API_PREFIX}/artifacts/${res.artifacts.commentary_txt}`
                            : undefined,
                    },
                    transcript_cues: res.artifacts.vtt
                        ? [] // We'll fetch VTT separately if needed, or backend can send cues
                        : [],
                };

                setData(transformed);
            } catch (err) {
                toast.error("Failed to load match details");
                console.error(err);
                navigate("/history");
            } finally {
                setLoading(false);
            }
        };
        fetchMatch();
    }, [matchId]);

    const { finalScore, events } = data
        ? mapRawToMatchEvents(data)
        : { finalScore: "0 - 0", events: [] };

    const homeTeam = { name: data?.home_team || "Home", logo: undefined };
    const awayTeam = { name: data?.away_team || "Away", logo: undefined };
    const players = data?.analysis.players || [];

    // If VTT exists, fetch and parse it
    const [transcriptCues, setTranscriptCues] = useState<TranscriptCue[]>([]);
    useEffect(() => {
        if (data?.artifacts?.vtt) {
            const vttUrl = `${API_BASE_URL}${API_PREFIX}/artifacts/${data.artifacts.vtt}`;
            fetch(vttUrl)
                .then((res) => res.text())
                .then((text) => {
                    const { vttToCues } = require("@/lib/vtt");
                    setTranscriptCues(vttToCues(text));
                })
                .catch((err) => {
                    console.warn("Failed to load VTT:", err);
                });
        }
    }, [data?.artifacts?.vtt]);

    const mediaSource: MediaSource = data?.artifacts?.media_url
        ? { type: "file", url: data.artifacts.media_url }
        : { type: "none" };

    if (loading) {
        return (
            <div className="flex items-center justify-center h-64">
                <div className="text-muted-foreground">Loading match...</div>
            </div>
        );
    }

    if (!data) {
        return null;
    }

    return (
        <div className="space-y-6">
            <div>
                <Button variant="ghost" size="sm" onClick={() => navigate("/history")} className="mb-4">
                    <ArrowLeft className="mr-2 h-4 w-4" />
                    Back to History
                </Button>
                <h1 className="text-2xl font-bold">Match Details</h1>
            </div>

            <Card>
                <CardHeader>
                    <CardTitle>Match Timeline</CardTitle>
                </CardHeader>
                <CardContent>
                    <MatchTimeline
                        homeTeam={homeTeam}
                        awayTeam={awayTeam}
                        finalScore={finalScore}
                        events={events}
                    />
                </CardContent>
            </Card>

            {players.length > 0 && (
                <TeamLineup homeTeam={homeTeam} awayTeam={awayTeam} players={players} />
            )}

            {transcriptCues.length > 0 && (
                <MediaTranscriptView source={mediaSource} cues={transcriptCues} />
            )}

            {/* Optional: Download links */}
            <Card>
                <CardHeader>
                    <CardTitle>Artifacts</CardTitle>
                </CardHeader>
                <CardContent className="flex flex-wrap gap-2">
                    {data?.artifacts?.excel && (
                        <Button asChild size="sm">
                            <a
                                href={`${API_BASE_URL}${API_PREFIX}/artifacts/${data.artifacts.excel}`}
                                download
                                target="_blank"
                                rel="noopener noreferrer"
                            >
                                Download Excel
                            </a>
                        </Button>
                    )}
                    {data?.artifacts?.events_csv && (
                        <Button asChild size="sm" variant="outline">
                            <a
                                href={`${API_BASE_URL}${API_PREFIX}/artifacts/${data.artifacts.events_csv}`}
                                download
                                target="_blank"
                                rel="noopener noreferrer"
                            >
                                Events CSV
                            </a>
                        </Button>
                    )}
                    {data?.artifacts?.players_csv && (
                        <Button asChild size="sm" variant="outline">
                            <a
                                href={`${API_BASE_URL}${API_PREFIX}/artifacts/${data.artifacts.players_csv}`}
                                download
                                target="_blank"
                                rel="noopener noreferrer"
                            >
                                Players CSV
                            </a>
                        </Button>
                    )}
                </CardContent>
            </Card>
        </div>
    );
}