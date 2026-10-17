import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { useApi } from "../api/useApi";
import type { ReportTurnView } from "../api/types";
import { Badge, Button, Card, Collapsible, Empty, Spinner } from "../components";
import { useInterviewReport } from "../interview/queries";
import { buildReportViewModel, clampScore } from "../interview/radar";
import { RadarChart } from "./interview/RadarChart";
import styles from "./InterviewReportPage.module.css";

//: What the backend writes for a category with too few scored questions (Q16).
const THIN_SAMPLE = "样本不足";

interface TurnGroup {
  key: string;
  head: ReportTurnView;
  turns: ReportTurnView[];
}

/** 逐题回放按主问题分组：同一 topic_no 的追问跟在其主问题之后。 */
function groupTurns(turns: ReportTurnView[]): TurnGroup[] {
  const groups: TurnGroup[] = [];
  for (const turn of turns) {
    const key = String(turn.topic_no);
    const last = groups[groups.length - 1];
    if (last && last.key === key) {
      last.turns.push(turn);
      continue;
    }
    groups.push({ key, head: turn, turns: [turn] });
  }
  return groups;
}

function TurnCard({ turn, nested }: { turn: ReportTurnView; nested: boolean }) {
  return (
    <article className={nested ? styles.turn + " " + styles.turnNested : styles.turn}>
      <header className={styles.turnHeader}>
        <span className={styles.turnNo} aria-label={"回放题号 " + turn.question_no}>
          {turn.question_no}
        </span>
        {turn.kind === "follow_up" ? <span className={styles.badge}>追问</span> : null}
        <span className={styles.turnScore}>
          {turn.score === null || turn.score === undefined ? "未作答" : turn.score.toFixed(1)}
        </span>
      </header>
      <p className={styles.question}>{turn.question}</p>
      {turn.answer ? <p className={styles.answer}>我的回答：{turn.answer}</p> : null}
      {turn.feedback ? <p className={styles.feedback}>{turn.feedback}</p> : null}
      {turn.missing_points && turn.missing_points.length > 0 ? (
        <p className={styles.missing}>缺失要点：{turn.missing_points.join("、")}</p>
      ) : null}
    </article>
  );
}

export function InterviewReportPage() {
  const api = useApi();
  const navigate = useNavigate();
  const { sessionId = "" } = useParams<{ sessionId: string }>();
  const reportQuery = useInterviewReport(api, sessionId);
  // 手动开合前为 null：默认只展开第一组，之后以显式集合为准。
  const [openKeys, setOpenKeys] = useState<string[] | null>(null);

  if (reportQuery.isLoading) {
    return (
      <div className={styles.loading}>
        <Spinner label="正在加载报告" />
      </div>
    );
  }

  if (reportQuery.isError || !reportQuery.data) {
    return (
      <div className={styles.page}>
        <Empty
          title="还没有报告"
          description="先结束面试，报告会自动生成。"
          action={
            <Button
              onClick={() => {
                Promise.resolve(navigate("/interview")).catch(() => undefined);
              }}
            >
              回到面试入口
            </Button>
          }
        />
      </div>
    );
  }

  const view = buildReportViewModel(reportQuery.data);
  // 后端边写边返回：summary_pending 为真时改进建议区显示等待态，不显示降级文案。
  const summaryPending = reportQuery.data.summary_pending;
  const categories = reportQuery.data.categories ?? [];
  const groups = groupTurns(view.turns);
  const firstGroup = groups[0];
  const open = new Set(openKeys ?? (firstGroup ? [firstGroup.key] : []));
  const allOpen = groups.length > 0 && groups.every((group) => open.has(group.key));

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div>
          <h2 className={styles.brand}>面试报告</h2>
          <p className={styles.meta}>
            共 {view.turns.length} 题 · 追问 {view.followUpCount} 次 · 会话 {sessionId.slice(0, 8)}
          </p>
        </div>
        <div className={styles.headerActions}>
          <Button
            variant="secondary"
            onClick={() => {
              Promise.resolve(navigate("/interview")).catch(() => undefined);
            }}
          >
            再面一次
          </Button>
          <Button
            variant="ghost"
            onClick={() => {
              Promise.resolve(navigate("/chat")).catch(() => undefined);
            }}
          >
            回到对话
          </Button>
        </div>
      </header>

      <Card title="综合表现" raised>
        <span className={styles.heroAccent} aria-hidden="true" />
        <div className={styles.heroMain}>
          <div className={styles.scoreBlock}>
            <p className={styles.scoreLabel}>综合得分</p>
            <p className={styles.overall} aria-label="综合得分">
              {view.overallScore === null ? "未评分" : view.overallScore.toFixed(1)}
            </p>
            {view.overallEstimated ? (
              <p className={styles.note}>本次没有有效评分，报告仅含过程记录。</p>
            ) : null}
            {view.dimensionsEstimated ? (
              <p className={styles.note}>维度缺失，已用综合分占位展示（非独立测算）。</p>
            ) : null}
          </div>
          <RadarChart dimensions={view.dimensions} />
        </div>
        {view.dimensions.length > 0 ? (
          <ul className={styles.dimensions} aria-label="四维小分">
            {view.dimensions.map((dimension) => (
              <li key={dimension.key} className={styles.dimension}>
                <span className={styles.dimensionLabel}>
                  {clampScore(dimension.score).toFixed(0)} {dimension.label}
                </span>
                <span className={styles.dimensionTrack} aria-hidden="true">
                  <span
                    className={styles.dimensionBar}
                    style={{ width: clampScore(dimension.score) + "%" }}
                  />
                </span>
              </li>
            ))}
          </ul>
        ) : null}
      </Card>

      <Card title="改进建议">
        {summaryPending ? (
          <p className={styles.summaryPending}>
            <Spinner label="正在生成总结" />
            <span>总结生成中…</span>
          </p>
        ) : view.summary ? (
          <p className={styles.summary}>{view.summary}</p>
        ) : (
          <p className={styles.note}>未生成总结（模型不可用或未配置），分数与逐题记录不受影响。</p>
        )}
        {view.suggestions.length > 0 ? (
          <ul className={styles.suggestions}>
            {view.suggestions.map((tip, index) => (
              <li key={tip} className={styles.suggestion}>
                <span className={styles.suggestionNo} aria-hidden="true">
                  {index + 1}
                </span>
                {tip}
              </li>
            ))}
          </ul>
        ) : null}
        {view.repeatedMissingPoints.length > 0 ? (
          <p className={styles.missing}>反复缺失：{view.repeatedMissingPoints.join("、")}</p>
        ) : null}
      </Card>

      {categories.length > 0 ? (
        <section className={styles.categories} aria-label="按类给分">
          <h2 className={styles.sectionTitle}>按类给分</h2>
          <ul className={styles.categoryGrid}>
            {categories.map((item) => (
              <li key={item.key}>
                <Card>
                  <div className={styles.categoryHead}>
                    <span className={styles.categoryBadge}>{item.label}</span>
                    {item.score === null || item.score === undefined ? (
                      <Badge tone="neutral">{THIN_SAMPLE}</Badge>
                    ) : (
                      <span className={styles.categoryScore} aria-label={item.label + "得分"}>
                        {item.score.toFixed(1)}
                      </span>
                    )}
                  </div>
                  <p className={styles.categoryMeta}>{item.count} 题</p>
                  {item.comment && item.comment !== THIN_SAMPLE ? (
                    <p className={styles.categoryComment}>{item.comment}</p>
                  ) : null}
                </Card>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <section className={styles.turns} aria-label="逐题回放">
        <div className={styles.turnsHeader}>
          <h2 className={styles.sectionTitle}>逐题回放</h2>
          {groups.length > 1 ? (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setOpenKeys(allOpen ? [] : groups.map((group) => group.key))}
            >
              {allOpen ? "全部收起" : "全部展开"}
            </Button>
          ) : null}
        </div>
        <div className={styles.turnGroups}>
          {groups.map((group) => (
            <div key={group.key} className={styles.turnGroup}>
              <Collapsible
                label={group.head.question}
                open={open.has(group.key)}
                onToggle={(next) => {
                  const chosen = new Set(open);
                  if (next) chosen.add(group.key);
                  else chosen.delete(group.key);
                  setOpenKeys([...chosen]);
                }}
              >
                <div className={styles.turnList}>
                  {group.turns.map((turn) => (
                    <TurnCard
                      key={turn.question_no}
                      turn={turn}
                      nested={turn.kind === "follow_up"}
                    />
                  ))}
                </div>
              </Collapsible>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
