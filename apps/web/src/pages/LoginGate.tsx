import { useState } from "react";
import type { UseMutationResult } from "@tanstack/react-query";

import type { Principal } from "../api/types";
import { Button, Card, Textarea } from "../components";
import styles from "./LoginGate.module.css";

export interface LoginGateProps {
  login: UseMutationResult<Principal, Error, string>;
}

/** M1 has no real accounts yet: a dev session keeps the demo honest and one click away. */
export function LoginGate({ login }: LoginGateProps) {
  const [userId, setUserId] = useState("");

  return (
    <div className={styles.gate}>
      <Card title="进入 better-resume">
        <p className={styles.hint}>
          还没有正式登录（M2 上线账号体系）。这里输入任意用户名即可创建本地会话。
        </p>
        <Textarea
          rows={1}
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
      </Card>
    </div>
  );
}
