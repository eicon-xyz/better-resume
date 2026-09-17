import { useCallback, useEffect, useRef, useState } from "react";
import type { KeyboardEvent } from "react";

import { Button, Textarea } from "../../components";
import { replaceTranscript } from "../../audio/transcriptStore";
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
  // The transcript text this composer contributed into the box; realtime partials replace
  // that span (P28) instead of re-appending the whole cumulative text each event.
  const spanRef = useRef("");

  const update = useCallback((text: string) => {
    valueRef.current = text;
    setValue(text);
  }, []);

  useEffect(() => {
    if (transcript.length === 0) {
      // session reset (new recording / store cleared): the old span is gone from the box
      spanRef.current = "";
      return;
    }
    const mergedValue = replaceTranscript(valueRef.current, spanRef.current, transcript);
    spanRef.current = transcript;
    setNotice(mergedValue.notice);
    if (mergedValue.text !== valueRef.current) update(mergedValue.text);
  }, [transcript, update]);

  function submit() {
    const trimmed = value.trim();
    if (!trimmed || streaming || disabled) return;
    spanRef.current = ""; // the contributed span leaves with the cleared box
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
