import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { describeApiError, isRetryableError } from "../api/errors";
import type { ModelView } from "../api/types";
import { useApi } from "../api/useApi";
import { mergeTranscript } from "../audio/transcriptStore";
import { useTranscription } from "../audio/useTranscription";
import { Button } from "../components";
import { DEFAULT_AUTH_EPOCH, flattenHistory, useChatHistory, useChatSessions, useModels } from "../chat/queries";
import { mergeHistory } from "../chat/selectors";
import { useChatStore } from "../chat/store";
import { useChatStream } from "../chat/useChatStream";
import { useSession } from "../chat/useSession";
import { useQueryClient } from "@tanstack/react-query";
import { chatKeys } from "../chat/queries";
import { Composer } from "./chat/Composer";
import { MessageList } from "./chat/MessageList";
import { SessionSidebar } from "./chat/SessionSidebar";
import { LoginGate } from "./LoginGate";
import styles from "./ChatPage.module.css";

export function ChatPage() {
  const api = useApi();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { sessionId = null } = useParams<{ sessionId?: string }>();
  const session = useSession(api);

  const sessionsQuery = useChatSessions(api, DEFAULT_AUTH_EPOCH, session.isAuthenticated);
  const modelsQuery = useModels(api, DEFAULT_AUTH_EPOCH, session.isAuthenticated);
  const historyQuery = useChatHistory(api, sessionId, DEFAULT_AUTH_EPOCH);

  const storeMessages = useChatStore((state) => state.messages);
  const [modelRef, setModelRef] = useState<string | null>(null);

  const [draft, setDraft] = useState("");
  const draftRef = useRef("");

  const onTranscript = useCallback((text: string) => {
    const merged = mergeTranscript(draftRef.current, text);
    if (merged.text !== draftRef.current) {
      draftRef.current = merged.text;
      setDraft(merged.text);
    }
  }, []);

  const transcription = useTranscription({ client: api, onTranscript });

  const controller = useChatStream({
    client: api,
    sessionId,
    onSessionCreated: (created) => {
      void navigate(`/chat/${created}`);
      void queryClient.invalidateQueries({ queryKey: chatKeys.sessions(DEFAULT_AUTH_EPOCH) });
    },
  });

  // Route changes reset run state, but never the session we just created here.
  useEffect(() => {
    if (useChatStore.getState().sessionId !== sessionId) {
      useChatStore.getState().openSession(sessionId);
    }
  }, [sessionId]);

  const messages = useMemo(
    () => mergeHistory(flattenHistory(historyQuery.data), storeMessages),
    [historyQuery.data, storeMessages],
  );

  if (session.isLoading) {
    return <p className={styles.loading}>正在检查登录状态…</p>;
  }

  if (!session.isAuthenticated) {
    return <LoginGate login={session.login} />;
  }

  const models: ModelView[] = modelsQuery.data ?? [];

  async function deleteSession(target: string) {
    await api.deleteChatSession(target);
    void queryClient.invalidateQueries({ queryKey: chatKeys.sessions(DEFAULT_AUTH_EPOCH) });
    if (target === sessionId) {
      useChatStore.getState().openSession(null);
      void navigate("/chat");
    }
  }

  return (
    <div className={styles.page}>
      <SessionSidebar
        sessions={sessionsQuery.data ?? []}
        activeId={sessionId}
        onSelect={(target) => {
          controller.cancel();
          void navigate(`/chat/${target}`);
        }}
        onCreate={() => {
          controller.cancel();
          useChatStore.getState().openSession(null);
          void navigate("/chat");
        }}
        onDelete={(target) => {
          void deleteSession(target);
        }}
      />

      <main className={styles.main}>
        <header className={styles.header}>
          <h1 className={styles.brand}>better-resume</h1>
          <div className={styles.headerControls}>
            <label className={styles.modelPicker}>
              模型
              <select
                aria-label="选择模型"
                value={modelRef ?? ""}
                onChange={(event) => {
                  setModelRef(event.target.value || null);
                }}
              >
                <option value="">默认</option>
                {models.map((model) => (
                  <option key={model.name} value={model.name} disabled={!model.configured}>
                    {model.name}
                    {model.configured ? "" : "（未配置密钥）"}
                  </option>
                ))}
              </select>
            </label>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => void navigate("/settings/ai")}
            >
              AI 设置
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                void api.logout().then(() => {
                  void queryClient.invalidateQueries();
                });
              }}
            >
              退出
            </Button>
          </div>
        </header>

        <div className={styles.messages}>
          {controller.failure ? (
            <p className={styles.error} role="alert">
              {describeApiError(controller.failure)}
              {isRetryableError(controller.failure) ? (
                <Button
                  variant="secondary"
                  size="sm"
                  loading={controller.streaming}
                  onClick={() => void controller.retry()}
                >
                  重试
                </Button>
              ) : null}
            </p>
          ) : null}

          {!controller.failure && historyQuery.isError ? (
            <p className={styles.error} role="alert">
              加载历史失败
            </p>
          ) : null}

          <MessageList
            messages={messages}
            streaming={controller.streaming}
            hasOlder={Boolean(historyQuery.hasNextPage)}
            loadingOlder={historyQuery.isFetchingNextPage}
            onLoadOlder={() => {
              void historyQuery.fetchNextPage();
            }}
          />
        </div>

        <Composer
          streaming={controller.streaming}
          transcript={draft}
          recording={transcription.recording}
          recordingError={transcription.error}
          onToggleRecording={() => {
            if (transcription.recording) transcription.stop();
            else void transcription.start();
          }}
          onSend={(content) => {
            draftRef.current = "";
            setDraft("");
            void controller.send(content, { modelRef });
          }}
          onCancel={() => {
            controller.cancel();
          }}
        />
      </main>
    </div>
  );
}
