// src/components/MediaTranscriptView.tsx
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import ReactPlayer from "react-player";
import TranscriptPanel from "@/components/TranscriptPanel";
import type { TranscriptCue } from "@/types/transcript";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Slider } from "@/components/ui/slider";
import { Play, Pause, SkipBack, SkipForward } from "lucide-react";

export type MediaSource =
  | { type: "youtube"; url: string }
  | { type: "file"; url: string } // pre-signed or local object URL
  | { type: "none" };

interface MediaTranscriptViewProps {
  source: MediaSource;
  cues: TranscriptCue[];
}

export default function MediaTranscriptView({ source, cues }: MediaTranscriptViewProps) {
  const playerRef = useRef<ReactPlayer | null>(null);
  const [playing, setPlaying] = useState(false);
  const [currentTimeMs, setCurrentTimeMs] = useState(0);
  const [pauseAtSegmentEnd, setPauseAtSegmentEnd] = useState(true);
  const [durationMs, setDurationMs] = useState(0);

  const valid = source.type !== "none" && (source as any).url;

  // Keep player time in ms
  const handleProgress = useCallback((state: { playedSeconds: number }) => {
    setCurrentTimeMs(Math.floor(state.playedSeconds * 1000));
  }, []);

  const handleDuration = useCallback((seconds: number) => {
    if (Number.isFinite(seconds)) setDurationMs(Math.floor(seconds * 1000));
  }, []);

  // Click-to-seek from transcript
  const handleSeek = useCallback((ms: number) => {
    const seconds = ms / 1000;
    playerRef.current?.seekTo(seconds, "seconds");
    setPlaying(true);
  }, []);

  // Auto-pause at segment end when actively playing
  const activeIndex = useMemo(() => {
    // binary search already used inside TranscriptPanel's helper; inline simple search here
    const t = currentTimeMs;
    let low = 0, high = cues.length - 1;
    while (low <= high) {
      const mid = (low + high) >>> 1;
      const c = cues[mid];
      if (t < c.startMs) high = mid - 1;
      else if (t >= c.endMs) low = mid + 1;
      else return mid;
    }
    return Math.max(0, Math.min(low, cues.length - 1));
  }, [currentTimeMs, cues]);

  useEffect(() => {
    if (!playing || !pauseAtSegmentEnd) return;
    const cue = cues[activeIndex];
    if (!cue) return;
    const remaining = cue.endMs - currentTimeMs;
    if (remaining <= 0) return;
    const id = setTimeout(() => {
      // Stop at the end of this segment to let the user read
      setPlaying(false);
    }, remaining + 5);
    return () => clearTimeout(id);
  }, [playing, currentTimeMs, activeIndex, cues, pauseAtSegmentEnd]);

  const seekToCue = (indexDelta: number) => {
    const target = Math.min(Math.max(activeIndex + indexDelta, 0), cues.length - 1);
    const cue = cues[target];
    if (!cue) return;
    handleSeek(cue.startMs);
  };

  const displayedDurationMs = useMemo(() => {
    if (durationMs > 0) return durationMs;
    const last = cues[cues.length - 1];
    return last ? last.endMs : 0;
  }, [durationMs, cues]);

  const handleScrub = (valueMs: number) => {
    if (!valid) return; // don't change text-only behavior
    const seconds = valueMs / 1000;
    playerRef.current?.seekTo(seconds, "seconds");
    setCurrentTimeMs(valueMs);
  };

  return (
    <Card className="w-full">
      <CardHeader className="pb-2">
        <CardTitle className="text-lg">Media & Transcript</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {/* Player column */}
          <div className="space-y-3">
            <div className="w-full">
              <div className="relative w-full aspect-video">
                <div className="absolute inset-0 rounded-md overflow-hidden bg-black/90">
                  {valid ? (
                    <ReactPlayer
                      ref={playerRef}
                      url={(source as any).url}
                      width="100%"
                      height="100%"
                      playing={playing}
                      controls={false}
                      onProgress={handleProgress}
                      onDuration={handleDuration}
                      onPlay={() => setPlaying(true)}
                      onPause={() => setPlaying(false)}
                      config={{ youtube: { playerVars: { rel: 0, modestbranding: 1, controls: 0 } } }}
                    />
                  ) : (
                    <div className="flex h-full w-full items-center justify-center text-muted-foreground">
                      No media available
                    </div>
                  )}
                </div>
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Button size="sm" variant="outline" onClick={() => seekToCue(-1)} disabled={activeIndex <= 0} aria-label="Previous segment">
                <SkipBack className="h-4 w-4" />
              </Button>
              {!playing ? (
                <Button size="sm" onClick={() => setPlaying(true)} disabled={!valid} aria-label="Play">
                  <Play className="h-4 w-4" />
                </Button>
              ) : (
                <Button size="sm" variant="destructive" onClick={() => setPlaying(false)} aria-label="Pause">
                  <Pause className="h-4 w-4" />
                </Button>
              )}
              <Button size="sm" variant="outline" onClick={() => seekToCue(1)} disabled={activeIndex >= cues.length - 1} aria-label="Next segment">
                <SkipForward className="h-4 w-4" />
              </Button>
              <Badge variant="outline" className="ml-auto">
                <span className="hidden sm:inline">{formatTime(currentTimeMs)} / {formatTime(displayedDurationMs)}</span>
                <span className="sm:hidden">{formatTime(currentTimeMs)}</span>
              </Badge>
              <Button
                size="sm"
                variant={pauseAtSegmentEnd ? "secondary" : "outline"}
                onClick={() => setPauseAtSegmentEnd(v => !v)}
                className="whitespace-nowrap"
              >
                {pauseAtSegmentEnd ? (
                  <>
                    <span className="hidden sm:inline">Pause each segment</span>
                    <span className="sm:hidden">Seg. pause</span>
                  </>
                ) : (
                  <>
                    <span className="hidden sm:inline">Play through</span>
                    <span className="sm:hidden">Play all</span>
                  </>
                )}
              </Button>
            </div>
            <div className="flex items-center gap-3">
              <Slider
                value={[Math.min(currentTimeMs, displayedDurationMs)]}
                min={0}
                max={Math.max(displayedDurationMs, 0)}
                step={500}
                onValueChange={([v]) => handleScrub(v)}
                disabled={!valid || displayedDurationMs <= 0}
              />
            </div>
          </div>

          {/* Transcript column (embedded) */}
          <TranscriptPanel cues={cues} currentTimeMs={currentTimeMs} onSeek={handleSeek} autoScroll embedded />
        </div>
      </CardContent>
    </Card>
  );
}

function formatTime(ms: number): string {
  const totalSecondsFloat = ms / 1000;
  const totalSeconds = Math.floor(totalSecondsFloat);
  const s = totalSeconds % 60;
  const m = Math.floor(totalSeconds / 60) % 60;
  const h = Math.floor(totalSeconds / 3600);
  const two = (n: number) => n.toString().padStart(2, "0");
  return h > 0 ? `${two(h)}:${two(m)}:${two(s)}` : `${two(m)}:${two(s)}`;
}
