import { useQueryClient } from "@tanstack/react-query";
import type { DragEvent, ReactNode } from "react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import type { InterviewSessionView } from "../api/types";
import { useApi } from "../api/useApi";
import { Badge, Button, Card, Empty, Input, Select } from "../components";
import { useSession } from "../chat/useSession";
import { interviewKeys, useInterviewSessions } from "../interview/queries";
import { INTERVIEW_TYPE_OPTIONS, interviewTypeLabel } from "../interview/interviewTypes";
import { MAX_RESUME_BYTES, useResumeUpload } from "../interview/useResumeUpload";
import { LoginGate } from "./LoginGate";
import { ResumePreviewCard } from "./interview/ResumePreviewCard";
import styles from "./InterviewIntroPage.module.css";

const RESUMABLE = new Set(["ready", "in_progress"]);

/** 面试侧重的逐行说明；原生 select 的 option 只渲染一行文本，说明接在同一行后面。 */
const INTERVIEW_TYPE_NOTES: Record<string, string> = {
  auto: "由简历内容自动决定考察侧重",
  fundamentals: "集中考察八股基础与原理",
  project: "围绕项目经历追问技术取舍",
  internship: "围绕实习经历追问工程细节",
};

/** 可继续会话的状态徽章文案，取值只有 ready 与 in_progress 两种。 */
const SESSION_STATUS_LABELS: Record<string, string> = {
  ready: "待开始",
  in_progress: "进行中",
};

/** 时间取接口返回串的前 16 位（YYYY-MM-DD HH:mm），不做时区换算，展示稳定可预测。 */
function formatSessionTime(iso: string): string {
  return iso.slice(0, 16).replace("T", " ");
}

/** 空态三步引导：序号写进标题文本，说明文案与图标都是静态内容。 */
const GUIDE_STEPS: { title: string; description: string; icon: ReactNode }[] = [
  {
    title: "1. 选择简历",
    description: "选择简历，填写岗位和可选 JD，生成一场专属模拟面试。",
    icon: (
      <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <path d="M14 3H7a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1V7z" />
        <path d="M14 3v4h4" />
        <path d="M9 13h6" />
        <path d="M9 17h4" />
      </svg>
    ),
  },
  {
    title: "2. 开始模拟",
    description: "系统准备面试计划与首题，随后进入实时语音逐轮答题。",
    icon: (
      <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <circle cx="12" cy="12" r="9" />
        <path d="M10 8.5 16 12l-6 3.5z" />
      </svg>
    ),
  },
  {
    title: "3. 生成报告",
    description: "完成模拟后生成专属面试报告，查看面试表现与改进建议。",
    icon: (
      <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <path d="M5 20v-7" />
        <path d="M12 20V5" />
        <path d="M19 20v-9" />
      </svg>
    ),
  },
];

export function InterviewIntroPage() {
  const api = useApi();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const session = useSession(api);
  const sessionsQuery = useInterviewSessions(api, session.isAuthenticated);
  const [interviewType, setInterviewType] = useState("auto");
  const [formOpen, setFormOpen] = useState(false);
  const upload = useResumeUpload({
    client: api,
    interviewType,
    onQuestionsReady: (sessionId) => {
      // Called from inside upload.start()'s own try/catch: a rejection here surfaces as upload.error.
      // Called from inside upload.start()'s try block: a rejection here surfaces as upload.error.
      queryClient
        .invalidateQueries({ queryKey: interviewKeys.sessions("local") })
        .catch(() => undefined);
      Promise.resolve(navigate(`/interview/room/${sessionId}`)).catch(() => undefined);
    },
  });

  if (session.isLoading) {
    return <p className={styles.loading}>正在检查登录状态…</p>;
  }
  if (!session.isAuthenticated) {
    return <LoginGate login={session.login} />;
  }

  const resumable = (sessionsQuery.data ?? []).filter((item) => RESUMABLE.has(item.status));
  const showEmptyState = !formOpen && resumable.length === 0;

  async function continueSession(item: InterviewSessionView) {
    try {
      await api.restoreInterview(item.id);
      await navigate(`/interview/room/${item.id}`);
    } catch {
      await sessionsQuery.refetch();
    }
  }

  function onDropFile(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    upload.selectFile(event.dataTransfer.files?.[0] ?? null).catch(() => undefined);
  }

  const busy = upload.stage === "uploading" || upload.stage === "generating";
  const percent = Math.round(upload.progress * 100);
  const stageLabel = upload.stage === "generating" ? "正在生成题目…" : "正在上传简历…";
  const resumeMb = Math.round(MAX_RESUME_BYTES / 1024 / 1024);

  /** 「继续上次面试」列表：有历史场次时常驻，卡片行观感。 */
  const historyList = resumable.length > 0 ? (
    <Card title="继续上次面试">
      <ul className={styles.sessions}>
        {resumable.map((item) => (
          <li key={item.id} className={styles.sessionRow}>
            <div className={styles.sessionInfo}>
              <span className={styles.sessionType}>{interviewTypeLabel(item.interview_type)}</span>
              <span className={styles.sessionMeta}>
                {item.question_count} 题 · {formatSessionTime(item.updated_at)}
              </span>
            </div>
            <div className={styles.sessionAction}>
              <Badge tone={item.status === "in_progress" ? "success" : "accent"}>
                {SESSION_STATUS_LABELS[item.status] ?? item.status}
              </Badge>
              <Button size="sm" variant="secondary" onClick={() => {
                continueSession(item).catch(() => undefined);
              }}>
                继续
              </Button>
            </div>
          </li>
        ))}
      </ul>
    </Card>
  ) : null;

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h2 className={styles.title}>模拟面试</h2>
        <p className={styles.subtitle}>免费额度：2 场</p>
      </header>

      <div className={styles.toolbar}>
        <Button
          onClick={() => {
            setFormOpen(true);
          }}
        >
          <svg
            className={styles.icon}
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
            aria-hidden="true"
          >
            <path d="M12 5v14" />
            <path d="M5 12h14" />
          </svg>
          创建模拟面试
        </Button>
      </div>

      {showEmptyState ? (
        <div className={styles.emptyState}>
          <svg className={styles.art} viewBox="0 0 160 120" aria-hidden="true">
            <ellipse className={styles.artFill} cx="80" cy="92" rx="56" ry="11" />
            <ellipse className={styles.artLine} cx="80" cy="92" rx="56" ry="11" />
            <path className={styles.artLine} d="M48 82c8-6 18-9 32-9s24 3 32 9" />
            <path className={styles.artLine} d="M62 52l-5-17 17 7" />
            <path className={styles.artLine} d="M98 52l5-17-17 7" />
            <circle className={styles.artFill} cx="80" cy="56" r="21" />
            <circle className={styles.artLine} cx="80" cy="56" r="21" />
            <circle className={styles.artDot} cx="72" cy="54" r="2.2" />
            <circle className={styles.artDot} cx="88" cy="54" r="2.2" />
            <path className={styles.artLine} d="M76 63c1.5 1.5 6.5 1.5 8 0" />
            <path className={styles.artLine} d="M52 58h-9" />
            <path className={styles.artLine} d="M53 65l-9 3" />
            <path className={styles.artLine} d="M108 58h9" />
            <path className={styles.artLine} d="M107 65l9 3" />
            <path className={styles.artSpark} d="M128 22l2.4 6.6 6.6 2.4-6.6 2.4-2.4 6.6-2.4-6.6-6.6-2.4 6.6-2.4z" />
          </svg>
          <p className={styles.emptyLead}>创建你的第一场模拟面试，开始结构化练习</p>
          <ol className={styles.steps}>
            {GUIDE_STEPS.map((step) => (
              <li key={step.title} className={styles.step}>
                <span className={styles.stepIcon} aria-hidden="true">
                  {step.icon}
                </span>
                <div className={styles.stepBody}>
                  <h3 className={styles.stepTitle}>{step.title}</h3>
                  <p className={styles.stepText}>{step.description}</p>
                </div>
              </li>
            ))}
          </ol>
          <Button
            onClick={() => {
              setFormOpen(true);
            }}
          >
            创建模拟面试
          </Button>
        </div>
      ) : null}

      {formOpen ? (
        <div className={styles.grid}>
          <Card title="第一步：上传简历" raised>
            <div className={styles.focus}>
              <label className={styles.focusLabel} htmlFor="interview-focus">
                面试侧重
              </label>
              <Select
                id="interview-focus"
                aria-label="面试侧重"
                value={interviewType}
                onChange={(event) => {
                  setInterviewType(event.target.value);
                }}
              >
                {INTERVIEW_TYPE_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label} · {INTERVIEW_TYPE_NOTES[option.value] ?? ""}
                  </option>
                ))}
              </Select>
            </div>

            <label
              className={styles.dropzone}
              onDragOver={(event) => {
                event.preventDefault();
              }}
              onDrop={onDropFile}
            >
              <Input
                type="file"
                accept="application/pdf,.pdf"
                aria-label="选择简历 PDF"
                onChange={(event) => {
                  upload.selectFile(event.target.files?.[0] ?? null).catch(() => undefined);
                }}
              />
              <span className={styles.dropIconWrap} aria-hidden="true">
                <svg
                  className={styles.dropIcon}
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.6"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M12 16V4" />
                  <path d="m7 9 5-5 5 5" />
                  <path d="M4 16v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" />
                </svg>
              </span>
              <span className={styles.dropTitle}>
                {upload.file ? upload.file.name : "拖拽 PDF 到此处，或点击选择"}
              </span>
              <span className={styles.dropMeta}>
                支持带文本层的 PDF（上限 {resumeMb}MB）；扫描件请先用 OCR 转成可复制文本
              </span>
            </label>

            {upload.previewUrl ? (
              <p className={styles.preview}>
                已选择本地文件（{Math.ceil((upload.file?.size ?? 0) / 1024)} KB）
              </p>
            ) : null}

            {busy ? (
              <div className={styles.progress} role="status">
                <div className={styles.progressHead}>
                  <span>{stageLabel}</span>
                  <span className={styles.progressValue}>{percent}%</span>
                </div>
                <div
                  className={styles.track}
                  role="progressbar"
                  aria-label="上传进度"
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={percent}
                >
                  <div className={styles.bar} style={{ width: percent + "%" }} />
                </div>
              </div>
            ) : null}

            {upload.error ? (
              <p className={styles.error} role="alert">
                {upload.error}
              </p>
            ) : null}

            <div className={styles.actions}>
              <Button
                loading={busy}
                disabled={!upload.file}
                onClick={() => {
                  upload.start().catch(() => undefined);
                }}
              >
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

            {resumable.length === 0 ? (
              <Card title="继续上次面试">
                <Empty
                  title="没有进行中的面试"
                  description="上传简历后即可开始一轮模拟面试"
                  action={
                    <span className={styles.emptyArt} aria-hidden="true">
                      <svg
                        className={styles.emptyIcon}
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="1.6"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      >
                        <path d="M4 7a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2z" />
                        <path d="M8 10h8" />
                        <path d="M8 14h5" />
                      </svg>
                    </span>
                  }
                />
              </Card>
            ) : null}
          </div>
        </div>
      ) : null}

      {historyList}
    </div>
  );
}
