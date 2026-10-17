import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { describeApiError, isRetryableError, toApiError } from "../api/errors";
import type { ModelView } from "../api/types";
import { useApi } from "../api/useApi";
import { replaceTranscript } from "../audio/transcriptStore";
import { useTranscription } from "../audio/useTranscription";
import { Button, Select } from "../components";
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
  const [actionError, setActionError] = useState<string | null>(null);
  const draftRef = useRef("");
  // The transcript text we contributed into the box; realtime events replace this span.
  const transcriptSpanRef = useRef("");

  const onTranscript = useCallback((text: string) => {
    const merged = replaceTranscript(draftRef.current, transcriptSpanRef.current, text);
    transcriptSpanRef.current = text;
    if (merged.text !== draftRef.current) {
      draftRef.current = merged.text;
      setDraft(merged.text);
    }
  }, []);

  const transcription = useTranscription({ client: api, onTranscript });

  /** navigate() returns `void | Promise<void>`; normalise it, report a rejection, never float it. */
  function go(to: string): void {
    Promise.resolve(navigate(to)).catch((caught: unknown) => {
      setActionError(describeApiError(toApiError(caught)));
    });
  }

  /** Same reporting for an action that owns its own error state (only an escaping throw lands here). */
  function reportFailure(action: Promise<unknown>): void {
    action.catch((caught: unknown) => {
      setActionError(describeApiError(toApiError(caught)));
    });
  }

  const controller = useChatStream({
    client: api,
    sessionId,
    onSessionCreated: (created) => {
      // Session creation succeeded; refreshing the list only rejects on programmer error.
      queryClient
        .invalidateQueries({ queryKey: chatKeys.sessions(DEFAULT_AUTH_EPOCH) })
        .catch(() => undefined);
      go(`/chat/${created}`);
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
  const activeSession = (sessionsQuery.data ?? []).find((item) => item.id === sessionId);

  if (session.isLoading) {
    return <p className={styles.loading}>正在检查登录状态…</p>;
  }

  if (!session.isAuthenticated) {
    return <LoginGate login={session.login} />;
  }

  const models: ModelView[] = modelsQuery.data ?? [];

  async function deleteSession(target: string) {
    setActionError(null);
    await api.deleteChatSession(target);
    await queryClient.invalidateQueries({ queryKey: chatKeys.sessions(DEFAULT_AUTH_EPOCH) });
    if (target === sessionId) {
      useChatStore.getState().openSession(null);
      go("/chat");
    }
  }

  return (
    <div className={styles.page}>
      <SessionSidebar
        sessions={sessionsQuery.data ?? []}
        activeId={sessionId}
        onSelect={(target) => {
          controller.cancel();
          go(`/chat/${target}`);
        }}
        onCreate={() => {
          controller.cancel();
          useChatStore.getState().openSession(null);
          go("/chat");
        }}
        onDelete={(target) => {
          reportFailure(deleteSession(target));
        }}
      />

      <main className={styles.main}>
        <div className={styles.contextBar}>
          {activeSession ? (
            <h2 className={styles.sessionTitle}>{activeSession.title || "未命名会话"}</h2>
          ) : null}
          <label className={styles.modelPicker}>
            模型
            <Select
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
            </Select>
          </label>
        </div>

        <div className={styles.messages}>
          {actionError ? (
            <p className={styles.error} role="alert">
              {actionError}
            </p>
          ) : null}

          {controller.failure ? (
            <p className={styles.error} role="alert">
              {describeApiError(controller.failure)}
              {isRetryableError(controller.failure) ? (
                <Button
                  variant="secondary"
                  size="sm"
                  loading={controller.streaming}
                  onClick={() => {
                    reportFailure(controller.retry());
                  }}
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
              // The query owns the failure: it lands in historyQuery.isError, not in the banner.
              historyQuery.fetchNextPage().then(
                () => undefined,
                () => undefined,
              );
            }}
            onSuggestion={(text) => {
              // chip 填入的是手写内容而非转写 span：清空 span，后续语音按首次贡献追加。
              transcriptSpanRef.current = "";
              draftRef.current = text;
              setDraft(text);
            }}
            onStartInterview={() => {
              go("/interview");
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
            else {
              transcriptSpanRef.current = "";
              // start() funnels every failure into transcription.error; only a throw reaches here.
              reportFailure(transcription.start());
            }
          }}
          onSend={(content) => {
            draftRef.current = "";
            setDraft("");
            // send() owns its failure (controller.failure renders the banner); only a throw reaches here.
            reportFailure(controller.send(content, { modelRef }));
          }}
          onCancel={() => {
            controller.cancel();
          }}
        />
      </main>
    </div>
  );
}
