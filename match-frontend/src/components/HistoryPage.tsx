// src/pages/HistoryPage.tsx
import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Link, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { History, Clock } from "lucide-react";
import { toast } from "sonner";
import { http } from "@/lib/http";
import { API_PREFIX } from "@/lib/config";

interface HistoryItem {
    match_uuid: string;
    home_team: string;
    away_team: string;
    match_date: string; // ISO date
}

export default function HistoryPage() {
    const [history, setHistory] = useState<HistoryItem[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const fetchHistory = async () => {
            try {
                const res = await http<{ history: HistoryItem[] }>({
                    path: `/history`,
                    method: "GET",
                });
                setHistory(res.history || []);
            } catch (err) {
                toast.error("Failed to load history");
                console.error(err);
            } finally {
                setLoading(false);
            }
        };
        fetchHistory();
    }, []);

    const formatDate = (iso: string) => {
        return new Date(iso).toLocaleDateString("en-US", {
            year: "numeric",
            month: "short",
            day: "numeric",
            hour: "2-digit",
            minute: "2-digit",
        });
    };

    return (
        <div className="space-y-6">
            <div>
                <h1 className="text-2xl font-bold">Analysis History</h1>
                <p className="text-muted-foreground">Previously analyzed matches</p>
            </div>

            {loading ? (
                <div className="text-center py-8 text-muted-foreground">Loading...</div>
            ) : history.length === 0 ? (
                <Card>
                    <CardContent className="py-8 text-center">
                        <History className="mx-auto h-8 w-8 text-muted-foreground mb-2" />
                        <p>No analyses found.</p>
                        <Button className="mt-4" asChild>
                            <Link to="/">Analyze a new match</Link>
                        </Button>
                    </CardContent>
                </Card>
            ) : (
                <div className="grid gap-4">
                    {history.map((item) => (
                        <Card key={item.match_uuid} className="hover:bg-accent/30 transition-colors">
                            <CardContent className="p-4">
                                <Link to={`/history/${item.match_uuid}`} className="block">
                                    <div className="flex items-center justify-between">
                                        <div>
                                            <div className="font-medium">
                                                {item.home_team} vs {item.away_team}
                                            </div>
                                            <div className="text-sm text-muted-foreground flex items-center gap-1 mt-1">
                                                <Clock className="h-3 w-3" />
                                                {formatDate(item.match_date)}
                                            </div>
                                        </div>
                                        <Button variant="ghost" size="sm">
                                            View
                                        </Button>
                                    </div>
                                </Link>
                            </CardContent>
                        </Card>
                    ))}
                </div>
            )}
        </div>
    );
}