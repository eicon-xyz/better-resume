/**
 * Transcript run state (D15): one channel feeds the interview answer box and the chat
 * composer. Server state stays in TanStack Query; this is the live text only.
 *
 * Wire note: the server sends {kind, text, seg_id}. "replace" rewrites the live area,
 * "archive" appends a finished sentence to the committed text, "final" is the closing
 * snapshot.
 */

import { create } from "zustand";

export interface TranscriptEvent {
  kind: "replace" | "archive" | "final";
  text: string;
  seg_id?: string | null;
}

export type TranscriptStatus = "idle" | "connecting" | "live" | "reconnecting" | "error" | "closed";

export interface TranscriptState {
  live: string;
  committed: string;
  status: TranscriptStatus;
  error: string | null;
  droppedFrames: number;

  applyEvent(event: TranscriptEvent): void;
  setStatus(status: TranscriptStatus, detail?: string | null): void;
  noteDroppedFrames(count: number): void;
  reset(): void;
}

export function mergeTranscript(local: string, merged: string): { text: string; notice: boolean } {
  if (merged.length === 0) return { text: local, notice: false };
  if (local.length === 0 || merged.startsWith(local)) return { text: merged, notice: false };
  // The same run arriving again (or the candidate edited around it): already in the box.
  if (local.includes(merged)) return { text: local, notice: false };
  // A batch vendor answers once per press with a whole utterance, so a transcript that is
  // not an evolution of what is in the box is new text: append it and never clobber the
  // candidate's own words (M4's rule dropped it, which made every press after the first
  // look like a no-op).
  return { text: `${local}${merged}`, notice: true };
}

const EMPTY = {
  live: "",
  committed: "",
  status: "idle" as TranscriptStatus,
  error: null,
  droppedFrames: 0,
};

export const useTranscriptStore = create<TranscriptState>()((set) => ({
  ...EMPTY,
  applyEvent: (event) =>
    set((state) => {
      if (event.kind === "replace") {
        return { live: event.text, error: null };
      }
      if (event.kind === "archive") {
        const next = state.committed.endsWith(event.text)
          ? state.committed
          : state.committed + event.text;
        return { committed: next, live: "", error: null };
      }
      return { live: "", committed: event.text, status: "closed" as TranscriptStatus };
    }),
  setStatus: (status, detail = null) => set({ status, error: detail }),
  noteDroppedFrames: (count) => set((state) => ({ droppedFrames: state.droppedFrames + count })),
  reset: () => set({ ...EMPTY }),
}));

export function transcriptText(state: Pick<TranscriptState, "live" | "committed">): string {
  return state.committed + state.live;
}
