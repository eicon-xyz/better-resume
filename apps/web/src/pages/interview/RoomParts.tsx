import { Button, Card, Textarea } from "../../components";
import type { InterviewTurn } from "../../interview/roomStore";
import styles from "./RoomParts.module.css";

export function QuestionCard({
  turn,
  onSpeak,
  speaking = false,
}: {
  turn: InterviewTurn;
  onSpeak?: (text: string) => void;
  speaking?: boolean;
}) {
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
      {onSpeak ? (
        <Button variant="ghost" size="sm" onClick={() => onSpeak(turn.question)}>
          {speaking ? "停止朗读" : "朗读题目"}
        </Button>
      ) : null}
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
  value: string;
  onChange: (text: string) => void;
  /** Resolves false when the backend rejected the answer: the text must stay put. */
  onSubmit: (text: string) => Promise<boolean> | boolean | void;
  recording?: boolean;
  onToggleRecording?: () => void;
  recordingError?: string | null;
  transcriptNotice?: boolean;
  micSupported?: boolean;
}

export function AnswerComposer({
  disabled,
  submitting,
  value,
  onChange,
  onSubmit,
  recording = false,
  onToggleRecording,
  recordingError = null,
  transcriptNotice = false,
  micSupported = true,
}: AnswerComposerProps) {
  return (
    <form
      className={styles.composer}
      onSubmit={(event) => {
        event.preventDefault();
        const trimmed = value.trim();
        if (!trimmed) return;
        // Clear only once the backend accepted it: a 429/503/504 must not eat the answer.
        void Promise.resolve(onSubmit(trimmed)).then((accepted) => {
          if (accepted !== false) onChange("");
        });
      }}
    >
      {recordingError ? (
        <p className={styles.error} role="alert">
          {recordingError}
        </p>
      ) : null}
      {transcriptNotice ? (
        <p className={styles.hint}>已保留你写的内容：新的转写追加在后面，请确认。</p>
      ) : null}
      <Textarea
        name="answer"
        aria-label="你的回答"
        value={value}
        onChange={(event) => onChange(event.target.value)}
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
        {onToggleRecording ? (
          <Button
            type="button"
            variant={recording ? "secondary" : "ghost"}
            size="sm"
            disabled={disabled || submitting || !micSupported}
            onClick={onToggleRecording}
            aria-pressed={recording}
          >
            {recording ? "停止录音" : "语音输入"}
          </Button>
        ) : null}
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
