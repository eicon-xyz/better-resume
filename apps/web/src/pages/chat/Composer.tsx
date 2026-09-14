import { useCallback, useEffect, useRef, useState } from "react";
import type { KeyboardEvent } from "react";

import { Button, Textarea } from "../../components";
import { mergeTranscript } from "../../audio/transcriptStore";
import styles from "./Composer.module.css";

export interface ComposerProps {
  streaming: boolean;
  /** Live transcript from the shared channel; merged when it extends what is typed. */
  transcript?: string;
  recording?: boolean;
  onToggleRecording?: () => void;
  recordingError?: string | null;
  disabled?: boolean;
  onSend: (content: string) => void;
  onCancel: () => void;
}

export function Composer({
  streaming,
  disabled = false,
  onSend,
  onCancel,
  transcript = "",
  recording = false,
  onToggleRecording,
  recordingError = null,
}: ComposerProps) {
  const [value, setValue] = useState("");
  const valueRef = useRef("");
  const [notice, setNotice] = useState(false);

  const update = useCallback((text: string) => {
    valueRef.current = text;
    setValue(text);
  }, []);

  useEffect(() => {
    if (!transcript) return;
    const mergedValue = mergeTranscript(valueRef.current, transcript);
    setNotice(mergedValue.notice);
    if (mergedValue.text !== valueRef.current) update(mergedValue.text);
  }, [transcript, update]);

  function submit() {
    const trimmed = value.trim();
    if (!trimmed || streaming || disabled) return;
    update("");
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
        onChange={(event) => update(event.target.value)}
        onKeyDown={handleKeyDown}
      />
      {recordingError ? (
        <p role="alert">{recordingError}</p>
      ) : null}
      {notice ? <p>已保留你写的内容，新的转写追加在后面。</p> : null}
      <div className={styles.actions}>
        {onToggleRecording ? (
          <Button
            type="button"
            variant={recording ? "secondary" : "ghost"}
            size="sm"
            onClick={onToggleRecording}
            aria-pressed={recording}
          >
            {recording ? "停止录音" : "语音输入"}
          </Button>
        ) : null}
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
