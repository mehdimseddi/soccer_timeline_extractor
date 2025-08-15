// src/lib/vtt.ts
// Minimal VTT to JSON cues converter and helpers
import type { TranscriptCue } from "@/types/transcript";

const TIMESTAMP_RE = /^(\d{1,2}):(\d{2}):(\d{2})\.(\d{3})$/; // HH:MM:SS.mmm

function parseTimestampToMs(s: string): number {
  // Support HH:MM:SS.mmm and MM:SS.mmm
  const hms = TIMESTAMP_RE.exec(s);
  if (hms) {
    const [, hh, mm, ss, ms] = hms;
    return (
      parseInt(hh, 10) * 3600 * 1000 +
      parseInt(mm, 10) * 60 * 1000 +
      parseInt(ss, 10) * 1000 +
      parseInt(ms, 10)
    );
  }
  // Try MM:SS.mmm
  const parts = s.split(":");
  if (parts.length === 2) {
    const [mm, rest] = parts;
    const [ss, ms] = rest.split(".");
    return parseInt(mm, 10) * 60 * 1000 + parseInt(ss, 10) * 1000 + parseInt(ms, 10);
  }
  return 0;
}

export function vttToCues(vttText: string): TranscriptCue[] {
  const lines = vttText.replace(/\r\n?/g, "\n").split("\n");
  const cues: TranscriptCue[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i].trim();
    if (!line || line === "WEBVTT") { i++; continue; }

    let id: string | undefined;
    let timing = line;

    // Optional identifier line before timing
    if (!line.includes("-->")) {
      id = line;
      i++;
      timing = (lines[i] || "").trim();
    }

    if (timing.includes("-->")) {
      const [startRaw, endRaw] = timing.split("-->").map(s => s.trim().split(" ")[0]);
      const startMs = parseTimestampToMs(startRaw);
      const endMs = parseTimestampToMs(endRaw);

      i++;
      const textLines: string[] = [];
      while (i < lines.length && lines[i].trim() !== "") {
        textLines.push(lines[i]);
        i++;
      }
      cues.push({ startMs, endMs, text: textLines.join("\n"), id });
    }

    // Skip empty separator
    while (i < lines.length && lines[i].trim() === "") i++;
  }
  return cues.sort((a, b) => a.startMs - b.startMs);
}

export function findActiveCueIndex(cues: TranscriptCue[], timeMs: number): number {
  // Binary search would be better for very long lists; linear is ok for small
  let low = 0;
  let high = cues.length - 1;
  while (low <= high) {
    const mid = (low + high) >>> 1;
    const c = cues[mid];
    if (timeMs < c.startMs) high = mid - 1;
    else if (timeMs >= c.endMs) low = mid + 1;
    else return mid;
  }
  return Math.max(0, Math.min(low, cues.length - 1));
}
