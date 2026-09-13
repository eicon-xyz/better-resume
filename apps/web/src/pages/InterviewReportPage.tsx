import { useNavigate, useParams } from "react-router-dom";

import { useApi } from "../api/useApi";
import { Button, Card, Empty, Spinner } from "../components";
import { useInterviewReport } from "../interview/queries";
import { buildReportViewModel } from "../interview/radar";
import { RadarChart } from "./interview/RadarChart";
import styles from "./InterviewReportPage.module.css";

export function InterviewReportPage() {
  const api = useApi();
  const navigate = useNavigate();
  const { sessionId = "" } = useParams<{ sessionId: string }>();
  const reportQuery = useInterviewReport(api, sessionId);

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
          action={<Button onClick={() => void navigate("/interview")}>回到面试入口</Button>}
        />
      </div>
    );
  }

  const view = buildReportViewModel(reportQuery.data);

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div>
          <h1 className={styles.brand}>面试报告</h1>
          <p className={styles.meta}>
            共 {view.turns.length} 题 · 追问 {view.followUpCount} 次 · 会话 {sessionId.slice(0, 8)}
          </p>
        </div>
        <div className={styles.headerActions}>
          <Button variant="secondary" onClick={() => void navigate("/interview")}>
            再面一次
          </Button>
          <Button variant="ghost" onClick={() => void navigate("/chat")}>
            回到对话
          </Button>
        </div>
      </header>

      <div className={styles.grid}>
        <Card title="综合表现">
          <p className={styles.overall} aria-label="综合得分">
            {view.overallScore === null ? "未评分" : view.overallScore.toFixed(1)}
          </p>
          {view.overallEstimated ? (
            <p className={styles.note}>本次没有有效评分，报告仅含过程记录。</p>
          ) : null}
          {view.dimensionsEstimated ? (
            <p className={styles.note}>维度缺失，已用综合分占位展示（非独立测算）。</p>
          ) : null}
          <RadarChart dimensions={view.dimensions} />
        </Card>

        <Card title="改进建议">
          {view.summary ? (
            <p className={styles.summary}>{view.summary}</p>
          ) : (
            <p className={styles.note}>未生成总结（模型不可用或未配置），分数与逐题记录不受影响。</p>
          )}
          {view.suggestions.length > 0 ? (
            <ul className={styles.suggestions}>
              {view.suggestions.map((tip) => (
                <li key={tip}>{tip}</li>
              ))}
            </ul>
          ) : null}
          {view.repeatedMissingPoints.length > 0 ? (
            <p className={styles.missing}>
              反复缺失：{view.repeatedMissingPoints.join("、")}
            </p>
          ) : null}
        </Card>
      </div>

      <section className={styles.turns} aria-label="逐题回放">
        <h2 className={styles.turnsTitle}>逐题回放</h2>
        {view.turns.map((turn) => (
          <article key={turn.question_no} className={styles.turn}>
            <header className={styles.turnHeader}>
              <span className={styles.turnNo} aria-label={`回放题号 ${turn.question_no}`}>
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
        ))}
      </section>
    </div>
  );
}
