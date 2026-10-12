import type { ReactNode, TableHTMLAttributes } from "react";

import styles from "./Table.module.css";

export interface TableProps extends TableHTMLAttributes<HTMLTableElement> {
  children: ReactNode;
}

/** 样式化表格：只给 <table> 套样式，thead/tbody/tr/th/td 结构由调用方原样提供。 */
export function Table({ children, ...rest }: TableProps) {
  return (
    <table {...rest} className={styles.table}>
      {children}
    </table>
  );
}
