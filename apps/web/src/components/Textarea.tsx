import type { TextareaHTMLAttributes } from "react";

import styles from "./Textarea.module.css";

export type TextareaProps = TextareaHTMLAttributes<HTMLTextAreaElement>;

export function Textarea({ rows = 3, ...rest }: TextareaProps) {
  return <textarea {...rest} rows={rows} className={styles.textarea} />;
}
