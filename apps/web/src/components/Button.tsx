import type { ButtonHTMLAttributes, ReactNode } from "react";

import styles from "./Button.module.css";

export type ButtonVariant = "primary" | "secondary" | "ghost";
export type ButtonSize = "sm" | "md";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  children: ReactNode;
}

export function Button({
  variant = "primary",
  size = "md",
  loading = false,
  disabled,
  children,
  ...rest
}: ButtonProps) {
  return (
    <button
      {...rest}
      className={`${styles.button} ${styles[variant]} ${styles[size]}`}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
    >
      {children}
    </button>
  );
}
