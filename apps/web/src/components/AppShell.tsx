import { useQueryClient } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";

import { useApi } from "../api/useApi";
import { useSession } from "../chat/useSession";
import { Button } from "./Button";
import styles from "./AppShell.module.css";

// 主导航只指向既有路由；新增页面不在这里扩项。
const NAV_ITEMS = [
  { to: "/chat", label: "对话" },
  { to: "/interview", label: "面试" },
  { to: "/settings/ai", label: "AI 设置" },
] as const;

function isActive(pathname: string, to: string): boolean {
  return pathname === to || pathname.startsWith(to + "/");
}

export interface AppShellProps {
  children: ReactNode;
}

/** 全局页壳：顶栏（产品名 + 主导航 + 用户区与退出）+ 居中内容容器。 */
export function AppShell({ children }: AppShellProps) {
  const api = useApi();
  const queryClient = useQueryClient();
  const session = useSession(api);
  const { pathname } = useLocation();
  // 对话页内容通栏贴边：内容容器去掉最大宽度与水平内边距，会话侧栏贴窗口左缘。
  const fullBleed = isActive(pathname, "/chat");
  // 登录门变体：/chat 与 /interview 未登录时渲染登录门，渐变底衬改由页壳承载，
  // 顶栏透明叠在渐变上、内容通栏，顶栏结构与导航语义不变。
  const gateRoute = isActive(pathname, "/chat") || isActive(pathname, "/interview");
  const gate = gateRoute && !session.isLoading && !session.isAuthenticated;

  return (
    <div className={[styles.shell, gate ? styles.shellGate : ""].join(" ")}>
      <header className={[styles.topbar, gate ? styles.topbarGate : ""].join(" ")}>
        <Link className={styles.brandLink} to="/chat">
          <h1 className={styles.brand}>better-resume</h1>
        </Link>
        <nav className={styles.nav} aria-label="主导航">
          {NAV_ITEMS.map((item) => {
            const active = isActive(pathname, item.to);
            return (
              <Link
                key={item.to}
                to={item.to}
                className={[styles.navLink, active ? styles.navActive : ""].join(" ")}
                aria-current={active ? "page" : undefined}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
        <div className={styles.user}>
          {session.isAuthenticated && session.principal ? (
            <span className={styles.userName}>{session.principal.user_id}</span>
          ) : null}
          {session.isAuthenticated ? (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                void api.logout().then(() => {
                  void queryClient.invalidateQueries();
                });
              }}
            >
              退出
            </Button>
          ) : null}
        </div>
      </header>
      <div
        className={[styles.content, fullBleed ? styles.contentFull : "", gate ? styles.contentGate : ""].join(
          " ",
        )}
      >
        {children}
      </div>
    </div>
  );
}
