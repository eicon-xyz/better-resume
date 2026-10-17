import { useMemo, useState } from "react";

import { Button, Input } from "../../components";
import type { ChatSessionView } from "../../api/types";
import { formatRelativeTime } from "./relativeTime";
import styles from "./SessionSidebar.module.css";

export interface SessionSidebarProps {
  sessions: ChatSessionView[];
  activeId: string | null;
  onSelect: (sessionId: string) => void;
  onCreate: () => void;
  onDelete: (sessionId: string) => void;
}

/** 聊天页会话侧栏（页内二级栏）：新建主按钮 + 本地搜索；窄屏在顶部折叠，≥1024 恢复为左侧定宽列。 */
export function SessionSidebar({
  sessions,
  activeId,
  onSelect,
  onCreate,
  onDelete,
}: SessionSidebarProps) {
  const [query, setQuery] = useState("");
  // 时钟只在挂载时读一次（惰性初始化）：相对时间是展示口径，不随每次渲染跳动。
  const [now] = useState(() => Date.now());

  // 纯前端过滤：对已加载会话做大小写不敏感的子串匹配，不发请求。
  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (needle.length === 0) return sessions;
    return sessions.filter((session) =>
      (session.title || "未命名会话").toLowerCase().includes(needle),
    );
  }, [query, sessions]);

  return (
    <aside className={styles.sidebar}>
      <h2 className={styles.title}>会话</h2>
      <Button onClick={onCreate}>＋ 新建对话</Button>
      <Input
        type="search"
        aria-label="搜索会话"
        placeholder="搜索会话"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
      />

      <details className={styles.details}>
        <summary className={styles.summary}>会话列表（{filtered.length}）</summary>
        {filtered.length === 0 ? (
          <p className={styles.emptyResult}>没有匹配的会话</p>
        ) : (
          <ul className={styles.list}>
            {filtered.map((session) => (
              <li key={session.id} className={styles.item}>
                <button
                  type="button"
                  className={[styles.session, session.id === activeId ? styles.active : ""].join(" ")}
                  aria-current={session.id === activeId ? "true" : undefined}
                  onClick={() => {
                    onSelect(session.id);
                  }}
                >
                  <span className={styles.sessionTitle}>{session.title || "未命名会话"}</span>
                  <span className={styles.sessionMeta}>
                    <span className={styles.time}>
                      {formatRelativeTime(session.updated_at, now)}
                    </span>
                    <span className={styles.count}>{session.message_count}</span>
                  </span>
                </button>
                <button
                  type="button"
                  className={styles.delete}
                  aria-label={"删除 " + (session.title || "未命名会话")}
                  onClick={() => {
                    onDelete(session.id);
                  }}
                >
                  ×
                </button>
              </li>
            ))}
          </ul>
        )}
      </details>
    </aside>
  );
}
