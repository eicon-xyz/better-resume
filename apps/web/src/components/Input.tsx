import type { InputHTMLAttributes } from "react";

import styles from "./Input.module.css";

export type InputProps = InputHTMLAttributes<HTMLInputElement>;

/** 样式化原生 input：value/onChange/type/aria-label 等 props 原样透传。 */
export function Input(props: InputProps) {
  return <input {...props} className={styles.input} />;
}
