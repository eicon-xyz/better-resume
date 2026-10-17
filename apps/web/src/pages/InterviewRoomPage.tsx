import { useCallback, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { useApi } from "../api/useApi";
import { replaceTranscript } from "../audio/transcriptStore";
import { useTranscription } from "../audio/useTranscription";
import { useTtsPlayback } from "../audio/useTtsPlayback";
import { Button, Empty, Spinner } from "../components";
import { useInterviewRoom } from "../interview/useInterviewRoom";
import { useRoomStore } from "../interview/roomStore";
import { AnswerComposer, CategoryBadge, FeedbackCard, ProgressBar, QuestionCard } from "./interview/RoomParts";
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
      // Called at the end of finish()'s try block: a rejected navigation surfaces as state.error.
      Promise.resolve(navigate(`/interview/report/${id}`)).catch(() => undefined);
    },
  });

  const [answer, setAnswer] = useState("");
  const [notice, setNotice] = useState(false);
  // 反馈区在窄屏默认折叠；断点块在 ≥1024 让它常显并隐掉开关。
  const [feedbackOpen, setFeedbackOpen] = useState(false);
  const answerRef = useRef("");
  // The transcript text we contributed into the box; realtime events replace this span.
  const transcriptSpanRef = useRef("");
  const speech = useTtsPlayback({ client: api });

  const changeAnswer = useCallback((text: string) => {
    answerRef.current = text;
    setAnswer(text);
  }, []);

  const onTranscript = useCallback((text: string) => {
    const merged = replaceTranscript(answerRef.current, transcriptSpanRef.current, text);
    transcriptSpanRef.current = text;
    setNotice(merged.notice);
    if (merged.text !== answerRef.current) changeAnswer(merged.text);
  }, [changeAnswer]);

  const transcription = useTranscription({ client: api, onTranscript });

  const answeredTurns = state.turns.filter((turn) => !turn.pending && turn.score !== null);
  const latestTurnIndex = answeredTurns.length - 1;
  const current = state.currentQuestion
    ? (state.turns.find((turn) => turn.questionNo === state.currentQuestion?.question_no) ?? null)
    : null;
  const category = state.currentQuestion?.category ?? null;

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

  const finished = state.flowStatus === "completed" || state.sessionStatus === "finished";

  return (
    <div className={styles.page}>
      <header className={styles.roomBar}>
        <ProgressBar answered={state.answered} total={state.totalQuestions} />
        <CategoryBadge category={category} />
        <div className={styles.roomActions}>
          <Button
            variant="secondary"
            loading={controller.finishing}
            onClick={() => {
              controller.finish().catch(() => undefined);
            }}
          >
            结束并生成报告
          </Button>
        </div>
      </header>

      {state.error ? (
        <p className={styles.error} role="alert">
          {state.error}
        </p>
      ) : null}

      {state.notices.length > 0 ? (
        <ul className={styles.notices} aria-label="本次出题提示">
          {state.notices.map((text) => (
            <li key={text}>{text}</li>
          ))}
        </ul>
      ) : null}

      <div className={styles.body}>
        <section className={styles.main} aria-label="当前题目">
          {current ? (
            <QuestionCard
              turn={current}
              category={category}
              speaking={speech.state === "playing"}
              onSpeak={(text) => {
                speech.speak(text).catch(() => undefined);
              }}
            />
          ) : (
            <Empty
              title={finished ? "面试已结束" : "没有待答题目"}
              description={finished ? "可以生成报告了" : "请从面试入口重新开始或继续"}
              action={
                finished ? (
                  <Button
                    onClick={() => {
                      controller.finish().catch(() => undefined);
                    }}
                  >
                    生成报告
                  </Button>
                ) : undefined
              }
            />
          )}
        </section>

        <aside className={styles.side} aria-label="历史反馈">
          <div className={styles.feedbackToggle}>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              aria-expanded={feedbackOpen}
              onClick={() => setFeedbackOpen((open) => !open)}
            >
              历史反馈（{answeredTurns.length}）
            </Button>
          </div>
          <div className={styles.feedbackBody} data-open={feedbackOpen ? "true" : undefined}>
            {answeredTurns.length === 0 ? (
              <p className={styles.hint}>提交第一题后，这里会显示评分与反馈。</p>
            ) : (
              <ol className={styles.feedbackList} aria-label="反馈时间线">
                {answeredTurns.map((turn, index) => (
                  <li
                    key={turn.questionNo}
                    className={styles.feedbackItem}
                    data-latest={index === latestTurnIndex ? "true" : undefined}
                  >
                    {index === latestTurnIndex ? <span className={styles.latestTag}>最新</span> : null}
                    <FeedbackCard turn={turn} />
                  </li>
                ))}
              </ol>
            )}
          </div>
        </aside>
      </div>

      <AnswerComposer
        disabled={!current || finished}
        submitting={state.submitting}
        value={answer}
        onChange={changeAnswer}
        onSubmit={async (text) => {
          const accepted = await controller.submitAnswer(text);
          if (accepted) {
            changeAnswer("");
            setNotice(false);
          }
          return accepted;
        }}
        recording={transcription.recording}
        onToggleRecording={() => {
          if (transcription.recording) transcription.stop();
          else {
            transcriptSpanRef.current = "";
            // start() funnels failures into transcription.error; catch only a synchronous throw.
            transcription.start().catch(() => undefined);
          }
        }}
        recordingError={transcription.error}
        micSupported={transcription.supported}
        transcriptNotice={notice}
      />
    </div>
  );
}
