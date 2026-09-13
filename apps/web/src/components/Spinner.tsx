import styles from "./Spinner.module.css";

export interface SpinnerProps {
  label?: string;
}

export function Spinner({ label = "加载中" }: SpinnerProps) {
  return (
    <span className={styles.spinner} role="status" aria-label={label}>
      <span className={styles.dot} />
    </span>
  );
}
