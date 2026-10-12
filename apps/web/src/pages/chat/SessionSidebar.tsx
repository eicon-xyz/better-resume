import { Button } from "../../components";
import type { ChatSessionView } from "../../api/types";
import styles from "./SessionSidebar.module.css";

export interface SessionSidebarProps {
  sessions: ChatSessionView[];
  activeId: string | null;
  onSelect: (sessionId: string) => void;
  onCreate: () => void;
  onDelete: (sessionId: string) => void;
}

/** 聊天页会话侧栏（页内二级栏）：窄屏在顶部折叠，≥1024 恢复为左侧定宽列。 */
export function SessionSidebar({
  sessions,
  activeId,
  onSelect,
  onCreate,
  onDelete,
}: SessionSidebarProps) {
  return (
    <aside className={styles.sidebar}>
      <div className={styles.header}>
        <h2 className={styles.title}>会话</h2>
        <Button size="sm" onClick={onCreate}>
          新建
        </Button>
      </div>

      <details className={styles.details}>
        <summary className={styles.summary}>会话列表（{sessions.length}）</summary>
        <ul className={styles.list}>
          {sessions.map((session) => (
            <li key={session.id} className={styles.item}>
              <button
                type="button"
                className={`${styles.session} ${session.id === activeId ? styles.active : ""}`}
                aria-current={session.id === activeId ? "true" : undefined}
                onClick={() => {
                  onSelect(session.id);
                }}
              >
                <span className={styles.sessionTitle}>{session.title || "未命名会话"}</span>
                <span className={styles.count}>{session.message_count}</span>
              </button>
              <button
                type="button"
                className={styles.delete}
                aria-label={`删除 ${session.title || "未命名会话"}`}
                onClick={() => {
                  onDelete(session.id);
                }}
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      </details>
    </aside>
  );
}
