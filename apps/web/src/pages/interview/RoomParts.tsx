import { Button, Card, Textarea } from "../../components";
import type { InterviewTurn } from "../../interview/roomStore";
import styles from "./RoomParts.module.css";

export function QuestionCard({ turn }: { turn: InterviewTurn }) {
  return (
    <Card title={turn.kind === "follow_up" ? "追问" : "当前题目"}>
      <div className={styles.questionHeader}>
        <span className={styles.questionNo} aria-label="当前题号">
          {turn.questionNo}
        </span>
        {turn.kind === "follow_up" ? (
          <span className={styles.badge} data-kind="followup">
            追问 · {turn.followUpReason ? REASON_LABELS[turn.followUpReason] ?? turn.followUpReason : "细节澄清"}
          </span>
        ) : null}
      </div>
      <p className={styles.questionText}>{turn.question}</p>
      {turn.focusPoints.length > 0 ? (
        <p className={styles.points}>考察要点：{turn.focusPoints.join("、")}</p>
      ) : null}
    </Card>
  );
}

const REASON_LABELS: Record<string, string> = {
  AI_SUGGESTED: "面试官想深入",
  LOW_SCORE: "上一题得分偏低",
  MISSING_POINTS: "有要点未覆盖",
  FOLLOW_UP_LIMIT_REACHED: "追问已达上限",
  INTERVIEW_COMPLETED: "面试已结束",
  NO_RULE_TRIGGER: "无需追问",
};

export function FeedbackCard({ turn }: { turn: InterviewTurn }) {
  return (
    <Card>
      <div className={styles.feedbackHeader}>
        <span className={styles.questionNo} aria-label={`历史题号 ${turn.questionNo}`}>
          {turn.questionNo}
        </span>
        <span className={styles.score} aria-label={`第 ${turn.questionNo} 题得分`}>
          {turn.score === null ? "未评分" : turn.score.toFixed(1)}
        </span>
      </div>
      <p className={styles.answer}>{turn.answer}</p>
      {turn.feedback ? <p className={styles.feedback}>{turn.feedback}</p> : null}
      {turn.missingPoints.length > 0 ? (
        <p className={styles.missing}>缺失要点：{turn.missingPoints.join("、")}</p>
      ) : null}
    </Card>
  );
}

export interface AnswerComposerProps {
  disabled: boolean;
  submitting: boolean;
  onSubmit: (text: string) => void;
}

export function AnswerComposer({ disabled, submitting, onSubmit }: AnswerComposerProps) {
  return (
    <form
      className={styles.composer}
      onSubmit={(event) => {
        event.preventDefault();
        const raw = new FormData(event.currentTarget).get("answer");
        const value = typeof raw === "string" ? raw : "";
        if (value.trim()) {
          onSubmit(value);
          event.currentTarget.reset();
        }
      }}
    >
      <Textarea
        name="answer"
        aria-label="你的回答"
        placeholder="用具体案例回答（Ctrl/Cmd + Enter 提交）"
        disabled={disabled || submitting}
        onKeyDown={(event) => {
          if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
            event.preventDefault();
            event.currentTarget.form?.requestSubmit();
          }
        }}
      />
      <div className={styles.actions}>
        <Button type="submit" loading={submitting} disabled={disabled || submitting}>
          提交回答
        </Button>
      </div>
    </form>
  );
}

export function ProgressBar({ answered, total }: { answered: number; total: number }) {
  const ratio = total > 0 ? Math.min(1, answered / total) : 0;
  return (
    <div className={styles.progress}>
      <div className={styles.progressBar} style={{ width: `${Math.round(ratio * 100)}%` }} />
      <span className={styles.progressLabel}>
        已答 {answered} / {total} 题
      </span>
    </div>
  );
}
