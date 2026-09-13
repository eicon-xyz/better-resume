import { useState } from "react";
import type { KeyboardEvent } from "react";

import { Button, Textarea } from "../../components";
import styles from "./Composer.module.css";

export interface ComposerProps {
  streaming: boolean;
  disabled?: boolean;
  onSend: (content: string) => void;
  onCancel: () => void;
}

export function Composer({ streaming, disabled = false, onSend, onCancel }: ComposerProps) {
  const [value, setValue] = useState("");

  function submit() {
    const trimmed = value.trim();
    if (!trimmed || streaming || disabled) return;
    setValue("");
    onSend(trimmed);
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  }

  return (
    <div className={styles.composer}>
      <Textarea
        aria-label="输入消息"
        placeholder="问点什么…（Enter 发送，Shift+Enter 换行）"
        value={value}
        disabled={disabled}
        onChange={(event) => {
          setValue(event.target.value);
        }}
        onKeyDown={handleKeyDown}
      />
      <div className={styles.actions}>
        {streaming ? (
          <Button variant="secondary" onClick={onCancel}>
            停止生成
          </Button>
        ) : (
          <Button onClick={submit} disabled={disabled || value.trim().length === 0}>
            发送
          </Button>
        )}
      </div>
    </div>
  );
}
