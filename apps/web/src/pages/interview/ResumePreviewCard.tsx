import { Card, Collapsible } from "../../components";
import type { QuestionBatchView } from "../../api/types";
import styles from "./ResumePreviewCard.module.css";

export interface ResumePreviewCardProps {
  batch: QuestionBatchView | null;
}

/** Shows what the deterministic parser extracted — never presented as AI output. */
export function ResumePreviewCard({ batch }: ResumePreviewCardProps) {
  if (!batch) return null;
  const score = batch.session.resume_score;
  const suggestions = batch.suggestions ?? [];

  return (
    <Card title="简历解析与题目">
      <p className={styles.source}>
        以下内容由**本地规则解析**得出（不经过 AI），出题才使用模型。
      </p>
      <dl className={styles.stats}>
        <div>
          <dt>题目数</dt>
          <dd>{batch.questions.length}</dd>
        </div>
        <div>
          <dt>简历评分</dt>
          <dd>{score === null || score === undefined ? "未评估" : score.toFixed(1)}</dd>
        </div>
      </dl>

      <Collapsible label="查看题目与考察要点" open onToggle={() => undefined}>
        <ol className={styles.questions}>
          {batch.questions.map((question) => (
            <li key={question.question_no}>
              <span className={styles.number}>{question.question_no}</span>
              <div>
                <p className={styles.text}>{question.text}</p>
                <p className={styles.points}>
                  考察：{(question.focus_points ?? []).join("、") || "未标注"}
                </p>
              </div>
            </li>
          ))}
        </ol>
      </Collapsible>

      {suggestions.length > 0 ? (
        <div className={styles.suggestions}>
          <h3>简历建议</h3>
          <ul>
            {suggestions.map((tip) => (
              <li key={tip}>{tip}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </Card>
  );
}
