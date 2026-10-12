import type { ReactNode } from "react";

import styles from "./Skeleton.module.css";

export interface SkeletonProps {
  loading: boolean;
  label?: string;
  lines?: number;
  children: ReactNode;
}

/** 骨架屏开关：loading 时渲染占位，结束后渲染真实内容。 */
export function Skeleton({ loading, label = "加载中", lines = 1, children }: SkeletonProps) {
  if (!loading) return <>{children}</>;
  return (
    <span className={styles.skeleton} role="status" aria-label={label}>
      {Array.from({ length: lines }, (_, index) => (
        <span key={index} className={styles.line} aria-hidden="true" />
      ))}
    </span>
  );
}
