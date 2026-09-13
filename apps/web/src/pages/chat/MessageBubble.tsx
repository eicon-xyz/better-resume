import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { Collapsible } from "../../components";
import type { ChatMessage } from "../../chat/store";
import styles from "./MessageBubble.module.css";

export interface MessageBubbleProps {
  message: ChatMessage;
  reasoningOpen: boolean;
  onToggleReasoning: (open: boolean) => void;
}

export function MessageBubble({ message, reasoningOpen, onToggleReasoning }: MessageBubbleProps) {
  const isAssistant = message.role === "assistant";
  const hasReasoning = message.reasoning.trim().length > 0;

  return (
    <article
      aria-label={isAssistant ? "AI 回答" : "我的消息"}
      className={`${styles.bubble} ${isAssistant ? styles.assistant : styles.user}`}
    >
      <div className={styles.meta}>
        <span className={styles.role}>{isAssistant ? "AI" : "我"}</span>
        {message.streaming ? <span className={styles.streaming}>生成中…</span> : null}
      </div>

      {hasReasoning ? (
        <Collapsible label="深度思考" open={reasoningOpen} onToggle={onToggleReasoning}>
          {message.reasoning}
        </Collapsible>
      ) : null}

      <div className={styles.content}>
        {isAssistant ? (
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
        ) : (
          <p>{message.content}</p>
        )}
        {message.streaming ? <span className={styles.cursor} aria-hidden="true" /> : null}
      </div>

      {message.error ? <p className={styles.error}>{message.error}</p> : null}
    </article>
  );
}
