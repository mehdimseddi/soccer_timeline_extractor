// src/components/AnalysisForm.tsx
import { useEffect, useMemo, useState } from "react";
import { analyzeCommentary, analyzeMedia, analyzeYoutube, listTeams } from "@/lib/api";
import { logger } from "@/lib/logger";
import MatchTimeline from "./MatchTimeline";
import type { MatchResultResponse } from "@/types/match";
import { mapRawToMatchEvents } from "@/lib/matchMapper";
import { FileUploader } from "@/components/ui/file-uploader";
import TeamLineup from "@/components/TeamLineup";
import type { TranscriptCue } from "@/types/transcript";
import { API_BASE_URL } from "@/lib/config";
import MediaTranscriptView from "@/components/MediaTranscriptView";

// shadcn imports
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Loader2, Send, History, FileText, UploadCloud } from "lucide-react";
import { Progress } from "@/components/ui/progress";
import { toast } from "sonner";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

export default function AnalysisForm() {
    const [commentary, setCommentary] = useState("");
    const [matchData, setMatchData] = useState<MatchResultResponse | null>(null);
    const [loading, setLoading] = useState(false);
    const [progress, setProgress] = useState(0);
    const [activeTab, setActiveTab] = useState("text");
    const [file, setFile] = useState<File | null>(null);
    const [localMediaUrl, setLocalMediaUrl] = useState<string | null>(null);
    const [youtubeUrl, setYoutubeUrl] = useState("");
    const [teams, setTeams] = useState<{ id: number; name: string }[]>([]);
    const [homeTeamId, setHomeTeamId] = useState<number | undefined>(undefined);
    const [awayTeamId, setAwayTeamId] = useState<number | undefined>(undefined);
    const [latencyMs, setLatencyMs] = useState<number | null>(null);
    const [secondsElapsed, setSecondsElapsed] = useState(0);


    // Load team options on mount
    useEffect(() => {
        (async () => {
            try {
                const data = await listTeams();
                setTeams(data);
            } catch (err) {
                logger.warn("Failed to load teams", err);
            }
        })();
    }, []);

    // Create object URL for local audio/video file to enable playback
    useEffect(() => {
        if (file && (file.type.startsWith("audio/") || file.type.startsWith("video/"))) {
            const url = URL.createObjectURL(file);
            setLocalMediaUrl(url);
            return () => {
                URL.revokeObjectURL(url);
            };
        }
        setLocalMediaUrl(null);
    }, [file]);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();

        if (activeTab === "file" && file) {
            if (file.type.startsWith('audio/') || file.type.startsWith('video/')) {
                return await handleMediaUpload(file);
            } else {
                try {
                    const content = await readFileAsText(file);
                    if (!content.trim()) {
                        toast.error("The file is empty");
                        return;
                    }
                    return await analyzeTextContent(content);
                } catch (readErr) {
                    const message = readErr instanceof Error ? readErr.message : "Failed to read file";
                    toast.error("File Read Error", { description: message });
                    return;
                }
            }
        }

        if (activeTab === "youtube") {
            if (!youtubeUrl.trim()) {
                toast.error("Please enter a YouTube link");
                return;
            }
            return await analyzeYoutubeLink(youtubeUrl.trim());
        }

        if (!commentary.trim()) {
            toast.error("Please provide commentary to analyze");
            return;
        }

        await analyzeTextContent(commentary);
    };

    const handleMediaUpload = async (file: File) => {
        setLoading(true);
        setProgress(0);
        setMatchData(null);
        setLatencyMs(null); // reset counter
        setSecondsElapsed(0); // reset counter
        let secondsTimer = setInterval(() => {
            setSecondsElapsed((prev) => prev + 1);
        }, 1000);

        const startTime = performance.now();
        const toastId = toast.loading("Uploading media file...", {
            description: "Processing your audio/video file"
        });

        const interval = setInterval(() => {
            setProgress((prev) => {
                if (prev >= 90) {
                    clearInterval(interval);
                    return prev;
                }
                return prev + 10;
            });
        }, 300);

        try {
            const data = await analyzeMedia(file, { home_team_id: homeTeamId, away_team_id: awayTeamId });
            const endTime = performance.now(); // stop timing
            setLatencyMs(Math.round(endTime - startTime)); // store latency
            setMatchData(data);
            setProgress(100);

            toast.success("Analysis Complete", {
                id: toastId,
                description: "Match events have been successfully extracted",
                duration: 3000,
            });
        } catch (err) {
            logger.error("Media analysis failed", err);
            const errorMessage = err instanceof Error ? err.message : "Analysis failed";
            toast.error("Analysis Error", {
                id: toastId,
                description: errorMessage,
                action: {
                    label: "Try again",
                    onClick: () => handleMediaUpload(file),
                },
                duration: 5000,
            });
        } finally {
            clearInterval(interval);
            clearInterval(secondsTimer);
            setLoading(false);
        }
    };

    const analyzeTextContent = async (content: string) => {
        setLoading(true);
        setProgress(0);
        setMatchData(null);
        setLatencyMs(null); // reset counter
        setSecondsElapsed(0); // reset counter
        let secondsTimer = setInterval(() => {
            setSecondsElapsed((prev) => prev + 1);
        }, 1000);
        const startTime = performance.now();
        const toastId = toast.loading("Analyzing commentary...", {
            description: "Processing your match data"
        });

        const interval = setInterval(() => {
            setProgress((prev) => {
                if (prev >= 90) {
                    clearInterval(interval);
                    return prev;
                }
                return prev + 10;
            });
        }, 300);

        try {
            const data = await analyzeCommentary({ commentary: content, home_team_id: homeTeamId, away_team_id: awayTeamId });
            const endTime = performance.now(); // stop timing
            setLatencyMs(Math.round(endTime - startTime)); // store latency
            setMatchData(data);
            setProgress(100);

            toast.success("Analysis Complete", {
                id: toastId,
                description: "Match events have been successfully extracted",
                duration: 3000,
            });
        } catch (err) {
            logger.error("Text analysis failed", err);
            const errorMessage = err instanceof Error ? err.message : "Analysis failed";
            toast.error("Analysis Error", {
                id: toastId,
                description: errorMessage,
                action: {
                    label: "Try again",
                    onClick: () => analyzeTextContent(content),
                },
                duration: 5000,
            });
        } finally {
            clearInterval(interval);
            clearInterval(secondsTimer);
            setLoading(false);
            setProgress(100);
        }
    };

    const analyzeYoutubeLink = async (url: string) => {
        setLoading(true);
        setProgress(0);
        setMatchData(null);
        setLatencyMs(null); // reset counter
        setSecondsElapsed(0); // reset counter
        let secondsTimer = setInterval(() => {
            setSecondsElapsed((prev) => prev + 1);
        }, 1000);
        const startTime = performance.now();

        const toastId = toast.loading("Analyzing YouTube link...", {
            description: "Fetching and processing the video"
        });

        const interval = setInterval(() => {
            setProgress((prev) => {
                if (prev >= 90) {
                    clearInterval(interval);
                    return prev;
                }
                return prev + 10;
            });
        }, 300);

        try {
            const data = await analyzeYoutube(url, { home_team_id: homeTeamId, away_team_id: awayTeamId });
            const endTime = performance.now(); // stop timing
            setLatencyMs(Math.round(endTime - startTime)); // store latency
            setMatchData(data);
            setProgress(100);

            toast.success("Analysis Complete", {
                id: toastId,
                description: "Match events have been successfully extracted",
                duration: 3000,
            });
        } catch (err) {
            logger.error("YouTube analysis failed", err);
            const errorMessage = err instanceof Error ? err.message : "Analysis failed";
            toast.error("Analysis Error", {
                id: toastId,
                description: errorMessage,
                action: {
                    label: "Try again",
                    onClick: () => analyzeYoutubeLink(url),
                },
                duration: 5000,
            });
        } finally {
            setLoading(false);
            clearInterval(secondsTimer);
            clearInterval(interval);
        }
    };

    const handleExampleClick = () => {
        setCommentary(`45+2' - GOAL! Manchester United 1-0 Liverpool. Bruno Fernandes scores with a brilliant strike from outside the box!
        56' - Yellow card for Virgil van Dijk after a late challenge on Marcus Rashford.
        78' - GOAL! Manchester United 2-0 Liverpool. Marcus Rashford doubles the lead with a clinical finish!
        89' - Substitution for Liverpool: Thiago Alcântara replaces Jordan Henderson.`);
        setActiveTab("text");
        setFile(null);
        setYoutubeUrl("");
    };

    const readFileAsText = (file: File): Promise<string> => {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = (event) => {
                if (event.target?.result) {
                    resolve(event.target.result as string);
                } else {
                    reject(new Error("Failed to read file"));
                }
            };
            reader.onerror = () => {
                reject(new Error("Error reading file"));
            };
            reader.readAsText(file);
        });
    };

    const toAbsolute = (url?: string | null): string | undefined => {
        if (!url) return undefined;
        try {
            // Ensure logos served by backend like "/artifacts/..." resolve against API_BASE_URL
            const abs = new URL(url, API_BASE_URL);
            return abs.toString();
        } catch {
            return url || undefined;
        }
    };

    const homeTeam = {
        name: matchData?.home_team || teams.find(t => t.id === homeTeamId)?.name || "Home Team",
        logo: toAbsolute(matchData?.home_team_logo_url),
    };
    const awayTeam = {
        name: matchData?.away_team || teams.find(t => t.id === awayTeamId)?.name || "Away Team",
        logo: toAbsolute(matchData?.away_team_logo_url),
    };
    const { finalScore, events } = matchData
        ? mapRawToMatchEvents(matchData)
        : { finalScore: "0 - 0", events: [] };
    const players = matchData?.analysis?.players ?? [];
    const transcriptCues: TranscriptCue[] = (matchData?.transcript_cues || []).map(c => ({
        startMs: c.start_ms,
        endMs: c.end_ms,
        text: c.text,
    }));
    // Determine media source from user input
    const mediaSource = useMemo(() => {
        // Prefer local file object URL when available
        if (localMediaUrl) return { type: "file", url: localMediaUrl } as const;
        // Else explicit media URL from backend artifacts
        const mediaUrl = matchData?.artifacts?.media_url;
        if (mediaUrl) return { type: "file", url: mediaUrl } as const;
        // Fallback to current user input when YouTube is used
        if (activeTab === "youtube" && youtubeUrl.trim()) {
            return { type: "youtube", url: youtubeUrl.trim() } as const;
        }
        return { type: "none" } as const;
    }, [localMediaUrl, matchData?.artifacts?.media_url, activeTab, youtubeUrl]);
    logger.debug("Analysis result:", events);
    return (
        <div className="space-y-6">
            <Card>
                <CardHeader>
                    <CardTitle className="text-xl">Analyze Commentary</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        <Select
                            value={homeTeamId != null ? String(homeTeamId) : ""}
                            onValueChange={(v) => setHomeTeamId(v ? Number(v) : undefined)}
                        >
                            <SelectTrigger className="w-full">
                                <SelectValue placeholder="Select home team" />
                            </SelectTrigger>
                            <SelectContent>
                                {teams.map((t) => (
                                    <SelectItem key={t.id} value={String(t.id)} dir="rtl">
                                        {t.name}
                                    </SelectItem>
                                ))}
                            </SelectContent>
                        </Select>

                        <Select
                            value={awayTeamId != null ? String(awayTeamId) : ""}
                            onValueChange={(v) => setAwayTeamId(v ? Number(v) : undefined)}
                        >
                            <SelectTrigger className="w-full">
                                <SelectValue placeholder="Select away team" />
                            </SelectTrigger>
                            <SelectContent>
                                {teams.map((t) => (
                                    <SelectItem key={t.id} value={String(t.id)} dir="rtl">
                                        {t.name}
                                    </SelectItem>
                                ))}
                            </SelectContent>
                        </Select>

                    </div>
                    <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
                        <TabsList className="grid w-full grid-cols-3">
                            <TabsTrigger value="text">
                                <FileText className="w-4 h-4 mr-2" />
                                Text Input
                            </TabsTrigger>
                            <TabsTrigger value="file">
                                <UploadCloud className="w-4 h-4 mr-2" />
                                File Upload
                            </TabsTrigger>
                            <TabsTrigger value="youtube">
                                {/* Using FileText icon for now; can change */}
                                <FileText className="w-4 h-4 mr-2" />
                                YouTube Link
                            </TabsTrigger>
                        </TabsList>

                        <TabsContent value="text" className="pt-4">
                            <Textarea
                                value={commentary}
                                onChange={(e) => setCommentary(e.target.value)}
                                placeholder="Paste match commentary here..."
                                className="min-h-32 max-h-40 resize-none overflow-auto p-3"
                                disabled={loading}
                            />
                        </TabsContent>

                        <TabsContent value="file" className="pt-4">
                            <FileUploader
                                value={file ? [file] : []}
                                onChange={(files) => setFile(files[0] || null)}
                                onRemove={() => setFile(null)}
                                isLoading={loading}
                            />
                        </TabsContent>

                        <TabsContent value="youtube" className="pt-4">
                            <div className="flex gap-2 items-center">
                                <input
                                    type="url"
                                    inputMode="url"
                                    placeholder="Paste YouTube URL..."
                                    className="flex-1 border-input bg-background placeholder:text-muted-foreground focus-visible:ring-ring h-10 w-full rounded-md border px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 disabled:cursor-not-allowed disabled:opacity-50"
                                    value={youtubeUrl}
                                    onChange={(e) => setYoutubeUrl(e.target.value)}
                                    disabled={loading}
                                />
                            </div>
                        </TabsContent>
                    </Tabs>

                    <div className="flex flex-col sm:flex-row gap-2">
                        <Button
                            type="submit"
                            className="w-full sm:w-auto sm:flex-1"
                            onClick={handleSubmit}
                            disabled={
                                loading ||
                                (activeTab === "file" && !file) ||
                                (activeTab === "youtube" && !youtubeUrl.trim())
                            }
                        >
                            {loading ? (
                                <>
                                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                    Analyzing...
                                </>
                            ) : (
                                <>
                                    <Send className="mr-2 h-4 w-4" />
                                    Analyze Match
                                </>
                            )}
                        </Button>

                        <Button
                            type="button"
                            variant="outline"
                            onClick={handleExampleClick}
                            disabled={loading}
                        >
                            <History className="mr-2 h-4 w-4" />
                            Load Example
                        </Button>
                    </div>

                    {loading && (
                        <Progress value={progress} className="h-2" />
                    )}
                    {loading ? (
                        <div className="text-sm text-muted-foreground">
                            Elapsed: {secondsElapsed} second{secondsElapsed !== 1 ? "s" : ""}
                        </div>
                    ) : latencyMs !== null && (
                        <div className="text-sm text-muted-foreground">
                            Total Time: {(latencyMs / 1000).toFixed(1)}s
                        </div>
                    )}


                </CardContent>
            </Card>

            {matchData && (
                <Card>
                    <CardHeader>
                        <CardTitle className="text-xl">Match Timeline</CardTitle>
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
            )}

            {players.length > 0 && (
                <TeamLineup homeTeam={homeTeam} awayTeam={awayTeam} players={players} />
            )}

            {transcriptCues.length > 0 && (
                <MediaTranscriptView source={mediaSource} cues={transcriptCues} />
            )}
        </div>
    );
}