import { useState } from "react";

import { Button, Empty } from "../../components";
import type { ChatMessage } from "../../chat/store";
import { MessageBubble } from "./MessageBubble";
import styles from "./MessageList.module.css";

export interface MessageListProps {
  messages: ChatMessage[];
  streaming: boolean;
  hasOlder: boolean;
  loadingOlder: boolean;
  onLoadOlder: () => void;
}

export function MessageList({
  messages,
  streaming,
  hasOlder,
  loadingOlder,
  onLoadOlder,
}: MessageListProps) {
  // Reasoning panels default to open (that is the "streaming shows thinking" behaviour);
  // collapsing is a per-message user choice, so no effect is needed.
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});

  if (messages.length === 0) {
    return (
      <Empty
        title="还没有消息"
        description={streaming ? "正在生成第一条回答…" : "在下面输入你的第一个问题"}
      />
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
