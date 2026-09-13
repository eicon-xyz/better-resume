import type { ReactNode } from "react";

import styles from "./Collapsible.module.css";

export interface CollapsibleProps {
  label: string;
  open: boolean;
  onToggle: (open: boolean) => void;
  children: ReactNode;
}

export function Collapsible({ label, open, onToggle, children }: CollapsibleProps) {
  return (
    <div className={styles.collapsible}>
      <button
        type="button"
        className={styles.trigger}
        aria-expanded={open}
        onClick={() => {
          onToggle(!open);
        }}
      >
        <span className={`${styles.chevron} ${open ? styles.chevronOpen : ""}`} aria-hidden="true" />
        {label}
      </button>
      {open ? (
        <div className={styles.content} role="region" aria-label={label}>
          {children}
        </div>
      ) : null}
    </div>
  );
}
