/** Radar geometry and report view model — pure functions, no DOM (easy to test). */

import type { DimensionView, InterviewReportView, ReportTurnView } from "../api/types";

export interface RadarPoint {
  key: string;
  label: string;
  score: number;
  x: number;
  y: number;
}

export interface RadarGeometry {
  center: number;
  radius: number;
  rings: number[];
  points: RadarPoint[];
  polygon: string;
}

const DIMENSION_LABELS: Record<string, string> = {
  accuracy: "准确性",
  depth: "深度",
  coverage: "要点覆盖",
  completeness: "完成度",
};

export const FALLBACK_DIMENSION_KEYS = ["accuracy", "depth", "coverage", "completeness"] as const;

export function clampScore(score: number): number {
  if (Number.isNaN(score)) return 0;
  return Math.min(100, Math.max(0, score));
}

/** Axis i sits at -90° + i·(360/n) so the first dimension points straight up. */
export function radarPoint(
  index: number,
  count: number,
  score: number,
  center: number,
  radius: number,
): { x: number; y: number } {
  const angle = (-Math.PI / 2) + (index * 2 * Math.PI) / Math.max(1, count);
  const distance = (radius * clampScore(score)) / 100;
  return {
    x: round(center + distance * Math.cos(angle)),
    y: round(center + distance * Math.sin(angle)),
  };
}

export function buildRadar(
  dimensions: DimensionView[],
  options: { center?: number; radius?: number; rings?: number[] } = {},
): RadarGeometry {
  const center = options.center ?? 110;
  const radius = options.radius ?? 84;
  const rings = options.rings ?? [25, 50, 75, 100];
  const count = dimensions.length;

  const points: RadarPoint[] = dimensions.map((dimension, index) => {
    const score = clampScore(dimension.score);
    const { x, y } = radarPoint(index, count, score, center, radius);
    return { key: dimension.key, label: dimension.label, score, x, y };
  });

  return {
    center,
    radius,
    rings,
    points,
    polygon: points.map((point) => `${point.x},${point.y}`).join(" "),
  };
}

export function ringPolygon(ring: number, options: { center?: number; radius?: number; axes: number }): string {
  const center = options.center ?? 110;
  const radius = options.radius ?? 84;
  const count = Math.max(3, options.axes);
  return Array.from({ length: count }, (_, index) => {
    const { x, y } = radarPoint(index, count, ring, center, radius);
    return `${x},${y}`;
  }).join(" ");
}

function round(value: number): number {
  return Math.round(value * 100) / 100;
}

export interface ReportViewModel {
  overallScore: number | null;
  overallEstimated: boolean;
  dimensions: DimensionView[];
  dimensionsEstimated: boolean;
  turns: ReportTurnView[];
  suggestions: string[];
  summary: string | null;
  summaryMissing: boolean;
  repeatedMissingPoints: string[];
  followUpCount: number;
}

export function buildReportViewModel(report: InterviewReportView): ReportViewModel {
  const rawDimensions = report.dimensions ?? [];
  const overall = report.overall_score ?? null;

  // Fallback: no dimensions but a score exists → show the score on every axis and say so.
  const dimensionFallback = rawDimensions.length === 0 && overall !== null;
  const dimensions: DimensionView[] = dimensionFallback
    ? FALLBACK_DIMENSION_KEYS.map((key) => ({
        key,
        label: DIMENSION_LABELS[key] ?? key,
        score: overall,
      }))
    : rawDimensions;

  const turns = report.turns ?? [];
  const counts = new Map<string, number>();
  for (const turn of turns) {
    for (const point of turn.missing_points ?? []) {
      counts.set(point, (counts.get(point) ?? 0) + 1);
    }
  }
  const repeatedMissingPoints = [...counts.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5)
    .map(([point]) => point);

  return {
    overallScore: overall,
    overallEstimated: overall === null,
    dimensions,
    dimensionsEstimated: dimensionFallback,
    turns,
    suggestions: report.suggestions ?? [],
    summary: report.summary ?? null,
    summaryMissing: !report.summary,
    repeatedMissingPoints,
    followUpCount: turns.filter((turn) => turn.kind === "follow_up").length,
  };
}
