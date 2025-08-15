// src/components/TranscriptPanel.tsx
import { useEffect, useMemo, useRef, useState } from "react";
import type { TranscriptCue } from "@/types/transcript";
import { findActiveCueIndex } from "@/lib/vtt";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

type TranscriptPanelProps = {
  cues: TranscriptCue[];
  currentTimeMs?: number; // optional; if undefined, panel won’t auto-highlight
  onSeek?: (ms: number) => void; // click on line to seek
  title?: string;
  autoScroll?: boolean;
  embedded?: boolean; // when true, render content without Card wrapper
};

export default function TranscriptPanel({ cues, currentTimeMs, onSeek, title = "Transcript", autoScroll = true, embedded = false }: TranscriptPanelProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [query, setQuery] = useState("");

  const filtered = useMemo(() => {
    if (!query.trim()) return cues;
    const q = query.trim().toLowerCase();
    return cues.filter(c => c.text.toLowerCase().includes(q));
  }, [cues, query]);

  const activeIndex = useMemo(() => {
    if (currentTimeMs == null) return -1;
    return findActiveCueIndex(cues, currentTimeMs);
  }, [cues, currentTimeMs]);

  useEffect(() => {
    if (!autoScroll) return;
    if (activeIndex < 0) return;
    const container = containerRef.current;
    if (!container) return;

    const node = container.querySelector<HTMLDivElement>(`[data-cue-index="${activeIndex}"]`);
    if (node) {
      node.scrollIntoView({ block: "center", behavior: "smooth" });
    }
  }, [activeIndex, autoScroll]);

  const content = (
    <>
      <div className="sticky top-0 z-10 bg-card pb-2">
        <Input
          placeholder="Search transcript…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label="Search transcript"
        />
      </div>
      <div ref={containerRef} className="max-h-[420px] overflow-y-auto rounded-md border p-2">
        {filtered.length === 0 ? (
          <div className="text-sm text-muted-foreground py-6 text-center">No matching lines.</div>
        ) : (
          filtered.map((cue, idx) => {
            const originalIndex = cues.indexOf(cue);
            const isActive = activeIndex === originalIndex;
            return (
              <div
                key={cue.id || `${cue.startMs}-${idx}`}
                data-cue-index={originalIndex}
                className={`flex gap-3 items-start rounded-md px-2 py-1.5 cursor-pointer transition-colors ${isActive ? "bg-primary/10 border border-primary/30" : "hover:bg-accent"}`}
                onClick={() => onSeek?.(cue.startMs)}
              >
                <div className="text-[11px] tabular-nums text-muted-foreground min-w-[72px] text-right">
                  {formatTime(cue.startMs)}
                </div>
                <div className="flex-1 whitespace-pre-wrap text-sm leading-relaxed">
                  {cue.text}
                </div>
              </div>
            );
          })
        )}
      </div>
    </>
  );

  if (embedded) {
    return <div className="space-y-3">{content}</div>;
  }

  return (
    <Card className="w-full">
      <CardHeader className="pb-2">
        <CardTitle className="text-lg">{title}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">{content}</CardContent>
    </Card>
  );
}

function formatTime(ms: number): string {
  const totalSecondsFloat = ms / 1000;
  const totalSeconds = Math.floor(totalSecondsFloat);
  const millis = Math.round((totalSecondsFloat - totalSeconds) * 1000);
  const s = totalSeconds % 60;
  const m = Math.floor(totalSeconds / 60) % 60;
  const h = Math.floor(totalSeconds / 3600);
  const two = (n: number) => n.toString().padStart(2, "0");
  const three = (n: number) => n.toString().padStart(3, "0");
  const base = h > 0 ? `${two(h)}:${two(m)}:${two(s)}` : `${two(m)}:${two(s)}`;
  return millis > 0 ? `${base}.${three(millis)}` : base;
}
