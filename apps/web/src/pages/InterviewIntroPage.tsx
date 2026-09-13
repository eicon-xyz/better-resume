import { useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";

import type { InterviewSessionView } from "../api/types";
import { useApi } from "../api/useApi";
import { Button, Card, Empty } from "../components";
import { useSession } from "../chat/useSession";
import { interviewKeys, useInterviewSessions } from "../interview/queries";
import { MAX_RESUME_BYTES, useResumeUpload } from "../interview/useResumeUpload";
import { LoginGate } from "./LoginGate";
import { ResumePreviewCard } from "./interview/ResumePreviewCard";
import styles from "./InterviewIntroPage.module.css";

const RESUMABLE = new Set(["ready", "in_progress"]);

export function InterviewIntroPage() {
  const api = useApi();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const session = useSession(api);
  const sessionsQuery = useInterviewSessions(api, session.isAuthenticated);
  const upload = useResumeUpload({
    client: api,
    onQuestionsReady: (sessionId) => {
      void queryClient.invalidateQueries({ queryKey: interviewKeys.sessions("local") });
      void navigate(`/interview/room/${sessionId}`);
    },
  });

  if (session.isLoading) {
    return <p className={styles.loading}>正在检查登录状态…</p>;
  }
  if (!session.isAuthenticated) {
    return <LoginGate login={session.login} />;
  }

  const resumable = (sessionsQuery.data ?? []).filter((item) => RESUMABLE.has(item.status));

  async function continueSession(item: InterviewSessionView) {
    try {
      await api.restoreInterview(item.id);
      void navigate(`/interview/room/${item.id}`);
    } catch {
      await sessionsQuery.refetch();
    }
  }

  const busy = upload.stage === "uploading" || upload.stage === "generating";

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.brand}>模拟面试</h1>
        <Link className={styles.back} to="/chat">
          返回对话
        </Link>
      </header>

      <div className={styles.grid}>
        <Card title="第一步：上传简历">
          <p className={styles.hint}>
            支持带文本层的 PDF（上限 {Math.round(MAX_RESUME_BYTES / 1024 / 1024)}MB）。
            扫描件请先用 OCR 转成可复制文本。
          </p>

          <label className={styles.dropzone}>
            <input
              type="file"
              accept="application/pdf,.pdf"
              aria-label="选择简历 PDF"
              onChange={(event) => {
                void upload.selectFile(event.target.files?.[0] ?? null);
              }}
            />
            <span>{upload.file ? upload.file.name : "点击选择 PDF 简历"}</span>
          </label>

          {upload.previewUrl ? (
            <p className={styles.preview}>
              已选择本地文件（{Math.ceil((upload.file?.size ?? 0) / 1024)} KB）
            </p>
          ) : null}

          {busy ? (
            <div className={styles.progress} role="status">
              <div
                className={styles.bar}
                style={{ width: `${Math.round(upload.progress * 100)}%` }}
                aria-label="上传进度"
              />
            </div>
          ) : null}

          {upload.error ? (
            <p className={styles.error} role="alert">
              {upload.error}
            </p>
          ) : null}

          <div className={styles.actions}>
            <Button loading={busy} disabled={!upload.file} onClick={() => void upload.start()}>
              {busy ? "正在生成题目…" : "开始面试"}
            </Button>
            <Button
              variant="ghost"
              disabled={busy || !upload.file}
              onClick={() => {
                upload.reset();
              }}
            >
              重新选择
            </Button>
          </div>
        </Card>

        <div className={styles.side}>
          <ResumePreviewCard batch={upload.batch} />

          <Card title="继续上次面试">
            {resumable.length === 0 ? (
              <Empty title="没有进行中的面试" description="上传简历后即可开始一轮模拟面试" />
            ) : (
              <ul className={styles.sessions}>
                {resumable.map((item) => (
                  <li key={item.id}>
                    <span>
                      {item.interview_type ?? "模拟面试"} · {item.question_count} 题 · {item.status}
                    </span>
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() => void continueSession(item)}
                    >
                      继续
                    </Button>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}
