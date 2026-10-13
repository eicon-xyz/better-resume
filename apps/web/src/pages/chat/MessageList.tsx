import { useState } from "react";

import { Button, Card, Empty } from "../../components";
import type { ChatMessage } from "../../chat/store";
import { MessageBubble } from "./MessageBubble";
import styles from "./MessageList.module.css";

/** 空态建议 chips：点击只把文案填进输入框，不发请求。 */
const SUGGESTIONS = [
  "出一套项目深挖题",
  "把一个技术取舍讲清楚",
  "五道八股基础题带答案要点",
  "准备 1 分钟自我介绍",
  "实习深挖题练手",
  "复盘一次失败经历怎么讲",
] as const;

export interface MessageListProps {
  messages: ChatMessage[];
  streaming: boolean;
  hasOlder: boolean;
  loadingOlder: boolean;
  onLoadOlder: () => void;
  /** 点击建议 chip：由页面把文案填进输入框。 */
  onSuggestion: (text: string) => void;
  /** 行动卡「去上传」：由页面做路由跳转。 */
  onStartInterview: () => void;
}

export function MessageList({
  messages,
  streaming,
  hasOlder,
  loadingOlder,
  onLoadOlder,
  onSuggestion,
  onStartInterview,
}: MessageListProps) {
  // Reasoning panels default to open (that is the "streaming shows thinking" behaviour);
  // collapsing is a per-message user choice, so no effect is needed.
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});

  if (messages.length === 0) {
    return (
      <div className={styles.empty}>
        <Empty
          title="还没有消息"
          description={streaming ? "正在生成第一条回答…" : undefined}
          action={
            <div className={styles.hero}>
              <h2 className={styles.greeting}>今天想练点什么？</h2>
              <p className={styles.note}>
                直接提问，或从下面的建议开始；要整套流程就上传简历，进模拟面试。
              </p>
              <ul className={styles.chips} aria-label="建议问题">
                {SUGGESTIONS.map((text) => (
                  <li key={text}>
                    <button
                      type="button"
                      className={styles.chip}
                      onClick={() => {
                        onSuggestion(text);
                      }}
                    >
                      {text}
                    </button>
                  </li>
                ))}
              </ul>
              <div className={styles.actionCard}>
                <Card raised title="上传简历，开始一轮模拟面试">
                  <p className={styles.actionNote}>AI 按简历出题、追问、评分，最后给报告</p>
                  <Button onClick={onStartInterview}>去上传</Button>
                </Card>
              </div>
            </div>
          }
        />
      </div>
    );
  }

  return (
    <div className={styles.list}>
      {hasOlder ? (
        <Button variant="ghost" size="sm" loading={loadingOlder} onClick={onLoadOlder}>
          加载更早的消息
        </Button>
      ) : null}

      {messages.map((message) => (
        <MessageBubble
          key={message.key}
          message={message}
          reasoningOpen={collapsed[message.key] !== true}
          onToggleReasoning={(open) =>
            setCollapsed((state) => ({ ...state, [message.key]: !open }))
          }
        />
      ))}
    </div>
  );
}
