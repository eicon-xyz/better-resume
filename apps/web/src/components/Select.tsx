import type { SelectHTMLAttributes } from "react";

import styles from "./Select.module.css";

export type SelectProps = SelectHTMLAttributes<HTMLSelectElement>;

/** 样式化原生 select：value/onChange/aria-label 等 props 原样透传，受控语义不变。 */
export function Select(props: SelectProps) {
  return <select {...props} className={styles.select} />;
}
