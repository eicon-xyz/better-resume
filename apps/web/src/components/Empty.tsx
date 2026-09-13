import type { ReactNode } from "react";

import styles from "./Empty.module.css";

export interface EmptyProps {
  title: string;
  description?: string;
  action?: ReactNode;
}

export function Empty({ title, description, action }: EmptyProps) {
  return (
    <div className={styles.empty}>
      <p className={styles.title}>{title}</p>
      {description ? <p className={styles.description}>{description}</p> : null}
      {action}
    </div>
  );
}
