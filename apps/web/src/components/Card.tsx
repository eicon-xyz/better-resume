import type { ReactNode } from "react";

import styles from "./Card.module.css";

export interface CardProps {
  title?: string;
  children: ReactNode;
  raised?: boolean;
}

export function Card({ title, children, raised = false }: CardProps) {
  return (
    <section className={`${styles.card} ${raised ? styles.raised : ""}`}>
      {title ? <h2 className={styles.title}>{title}</h2> : null}
      {children}
    </section>
  );
}
