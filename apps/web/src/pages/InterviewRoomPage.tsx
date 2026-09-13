import { useNavigate, useParams } from "react-router-dom";

import { useApi } from "../api/useApi";
import { Button, Empty, Spinner } from "../components";
import { useInterviewRoom } from "../interview/useInterviewRoom";
import { useRoomStore } from "../interview/roomStore";
import { AnswerComposer, FeedbackCard, ProgressBar, QuestionCard } from "./interview/RoomParts";
import styles from "./InterviewRoomPage.module.css";

export function InterviewRoomPage() {
  const api = useApi();
  const navigate = useNavigate();
  const { sessionId = "" } = useParams<{ sessionId: string }>();
  const state = useRoomStore();
  const controller = useInterviewRoom({
    client: api,
    sessionId,
    onFinished: (id) => {
      void navigate(`/interview/report/${id}`);
    },
  });

  const answeredTurns = state.turns.filter((turn) => !turn.pending && turn.score !== null);
  const current = state.currentQuestion
    ? (state.turns.find((turn) => turn.questionNo === state.currentQuestion?.question_no) ?? null)
    : null;

  if (controller.restoring) {
    return (
      <div className={styles.loading}>
        <Spinner label="正在恢复面试" />
      </div>
    );
  }

  if (controller.restoreError) {
    return (
      <div className={styles.page}>
        <Empty
          title="无法恢复这场面试"
          description={controller.restoreError}
          action={<Button onClick={() => void navigate("/interview")}>回到面试入口</Button>}
        />
      </div>
    );
  }

  const finished = state.flowStatus === "completed" || state.sessionStatus === "finished";

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div>
          <h1 className={styles.brand}>模拟面试</h1>
          <ProgressBar answered={state.answered} total={state.totalQuestions} />
        </div>
        <Button
          variant="secondary"
          loading={controller.finishing}
          onClick={() => void controller.finish()}
        >
          结束并生成报告
        </Button>
      </header>

      {state.error ? (
        <p className={styles.error} role="alert">
          {state.error}
        </p>
      ) : null}

      <div className={styles.body}>
        <section className={styles.main} aria-label="当前题目">
          {current ? (
            <QuestionCard turn={current} />
          ) : (
            <Empty
              title={finished ? "面试已结束" : "没有待答题目"}
              description={finished ? "可以生成报告了" : "请从面试入口重新开始或继续"}
              action={
                finished ? (
                  <Button onClick={() => void controller.finish()}>生成报告</Button>
                ) : undefined
              }
            />
          )}
        </section>

        <aside className={styles.side} aria-label="历史反馈">
          {answeredTurns.length === 0 ? (
            <p className={styles.hint}>提交第一题后，这里会显示评分与反馈。</p>
          ) : (
            answeredTurns.map((turn) => <FeedbackCard key={turn.questionNo} turn={turn} />)
          )}
        </aside>
      </div>

      <AnswerComposer
        disabled={!current || finished}
        submitting={state.submitting}
        onSubmit={(text) => controller.submitAnswer(text)}
      />
    </div>
  );
}
