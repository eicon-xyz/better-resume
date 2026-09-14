import { describe, expect, it } from "vitest";

import type { InterviewReportView } from "../api/types";
import { buildRadar, buildReportViewModel, clampScore, radarPoint, ringPolygon } from "./radar";

function dimension(key: string, label: string, score: number) {
  return { key, label, score };
}

const FOUR = [
  dimension("accuracy", "准确性", 80),
  dimension("depth", "深度", 60),
  dimension("coverage", "要点覆盖", 40),
  dimension("completeness", "完成度", 100),
];

describe("radarPoint", () => {
  it("puts the first axis straight up and walks clockwise", () => {
    const center = 100;
    const radius = 50;

    expect(radarPoint(0, 4, 100, center, radius)).toEqual({ x: 100, y: 50 });
    expect(radarPoint(1, 4, 100, center, radius)).toEqual({ x: 150, y: 100 });
    expect(radarPoint(2, 4, 100, center, radius)).toEqual({ x: 100, y: 150 });
    expect(radarPoint(3, 4, 100, center, radius)).toEqual({ x: 50, y: 100 });
  });

  it("collapses everything to the centre at zero", () => {
    for (let index = 0; index < 4; index += 1) {
      expect(radarPoint(index, 4, 0, 100, 50)).toEqual({ x: 100, y: 100 });
    }
  });

  it("clamps out-of-range scores", () => {
    expect(clampScore(-20)).toBe(0);
    expect(clampScore(180)).toBe(100);
    expect(clampScore(Number.NaN)).toBe(0);
    expect(radarPoint(0, 4, 180, 100, 50)).toEqual(radarPoint(0, 4, 100, 100, 50));
  });

  it("scales half marks to half the radius", () => {
    expect(radarPoint(0, 4, 50, 100, 50)).toEqual({ x: 100, y: 75 });
  });
});

describe("buildRadar", () => {
  it("builds a polygon with one point per dimension", () => {
    const radar = buildRadar(FOUR, { center: 100, radius: 50 });

    expect(radar.points).toHaveLength(4);
    expect(radar.polygon.split(" ")).toHaveLength(4);
    expect(radar.points[3]?.score).toBe(100);
    expect(radar.rings).toEqual([25, 50, 75, 100]);
  });

  it("draws ring polygons with one vertex per axis", () => {
    const ring = ringPolygon(100, { axes: 4, center: 100, radius: 50 });

    expect(ring.split(" ")).toHaveLength(4);
    expect(ring).toContain("100,50");
  });
});

function reportView(overrides: Partial<InterviewReportView> = {}): InterviewReportView {
  return {
    session: {
      id: "s-1",
      status: "finished",
      interview_type: null,
      question_count: 2,
      resume_score: 70,
      created_at: "2026-09-13T00:00:00Z",
      updated_at: "2026-09-13T00:00:00Z",
    },
    overall_score: 72.5,
    dimensions: FOUR,
    turns: [
      {
        question_no: "1",
        topic_no: 1,
        follow_up_index: 0,
        kind: "main",
        question: "第一题",
        answer: "回答一",
        score: 72.5,
        feedback: "不错",
        missing_points: ["量化"],
        follow_up_reason: "MISSING_POINTS",
      },
      {
        question_no: "1-F1",
        topic_no: 1,
        follow_up_index: 1,
        kind: "follow_up",
        question: "追问一",
        answer: "回答二",
        score: 60,
        feedback: "还差一点",
        missing_points: ["量化", "取舍"],
        follow_up_reason: null,
      },
    ],
    suggestions: ["补充量化结果"],
    summary: "整体不错",
    llm_summary_used: true,
    summary_pending: false,
    ...overrides,
  };
}

describe("buildReportViewModel", () => {
  it("maps the backend payload", () => {
    const view = buildReportViewModel(reportView());

    expect(view.overallScore).toBe(72.5);
    expect(view.overallEstimated).toBe(false);
    expect(view.dimensionsEstimated).toBe(false);
    expect(view.followUpCount).toBe(1);
    expect(view.summary).toBe("整体不错");
    expect(view.summaryMissing).toBe(false);
    expect(view.repeatedMissingPoints).toEqual(["量化", "取舍"]);
  });

  it("synthesises dimensions from the overall score when they are missing", () => {
    const view = buildReportViewModel(reportView({ dimensions: [] }));

    expect(view.dimensions).toHaveLength(4);
    expect(view.dimensions.every((item) => item.score === 72.5)).toBe(true);
    expect(view.dimensionsEstimated).toBe(true);
  });

  it("flags a missing summary without touching the numbers", () => {
    const view = buildReportViewModel(reportView({ summary: null }));

    expect(view.summaryMissing).toBe(true);
    expect(view.summary).toBeNull();
    expect(view.overallScore).toBe(72.5);
  });

  it("marks a report without any score as estimated", () => {
    const view = buildReportViewModel(reportView({ overall_score: null }));

    expect(view.overallEstimated).toBe(true);
  });

  it("tolerates missing turns and suggestions", () => {
    const view = buildReportViewModel(reportView({ turns: [], suggestions: [] }));

    expect(view.turns).toEqual([]);
    expect(view.repeatedMissingPoints).toEqual([]);
    expect(view.followUpCount).toBe(0);
  });
});
