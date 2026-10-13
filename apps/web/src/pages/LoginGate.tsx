import { useState } from "react";
import type { UseMutationResult } from "@tanstack/react-query";

import type { Principal } from "../api/types";
import { Button, Input } from "../components";
import styles from "./LoginGate.module.css";

export interface LoginGateProps {
  login: UseMutationResult<Principal, Error, string>;
}

/** M1 还没有正式账号体系：这里的本地会话就是「登录」，demo 兜底保持一键可达。 */
export function LoginGate({ login }: LoginGateProps) {
  const [userId, setUserId] = useState("");

  return (
    <div className={styles.gate}>
      <header className={styles.hero}>
        <h1 className={styles.title}>better-resume</h1>
        <p className={styles.tagline}>上传简历，AI 出题、追问、评分，把面试练到能上场。</p>
      </header>
      <section className={styles.card}>
        <span className={styles.cardSurface} aria-hidden="true" />
        <div className={styles.cardBody}>
          <p className={styles.hint}>还没有正式登录（M2 上线账号体系）。这里输入任意用户名即可创建本地会话。</p>
          <Input
            aria-label="用户名"
            placeholder="例如 demo"
            value={userId}
            onChange={(event) => {
              setUserId(event.target.value);
            }}
          />
          <div className={styles.actions}>
            <Button
              loading={login.isPending}
              onClick={() => {
                login.mutate(userId.trim() || "demo");
              }}
            >
              进入
            </Button>
          </div>
          {login.isError ? (
            <p className={styles.error} role="alert">
              登录失败：{login.error.message}
            </p>
          ) : null}
        </div>
      </section>
    </div>
  );
}