import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import type { ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";

import { useApi } from "../api/useApi";
import { useSession } from "../chat/useSession";
import { Button } from "./Button";
import {
  BookIcon,
  BrandMark,
  CalendarIcon,
  ChatIcon,
  ExternalIcon,
  GearIcon,
  PanelIcon,
  QuestionIcon,
  SparkIcon,
  TargetIcon,
  UserIcon,
} from "./Icons";
import styles from "./AppShell.module.css";

/** 主导航：图标 + 文案，active 以路由前缀判定。 */
const PRIMARY_NAV = [
  { to: "/coming-soon/interview-assist", label: "面试辅助", icon: CalendarIcon },
  { to: "/coming-soon/knowledge-base", label: "定制知识库", icon: BookIcon },
  { to: "/interview", label: "模拟面试", icon: TargetIcon },
  { to: "/resumes", label: "我的简历", icon: UserIcon },
] as const;

/** 次级导航：带外链样式图标，点进去仍是站内占位页。 */
const SECONDARY_NAV = [
  { to: "/coming-soon/user-manual", label: "用户手册", icon: QuestionIcon },
  { to: "/coming-soon/whats-new", label: "最新更新", icon: SparkIcon },
] as const;

function isActive(pathname: string, to: string): boolean {
  return pathname === to || pathname.startsWith(to + "/");
}

export interface AppShellProps {
  children: ReactNode;
}

/** 全局页壳：左侧栏（品牌 + 主导航 + 次级导航 + 账号行）+ 内容列 + 右下角对话气泡。
    登录门变体只保留品牌区与折叠按钮，登录面仍在页面自己渲染。 */
export function AppShell({ children }: AppShellProps) {
  const api = useApi();
  const queryClient = useQueryClient();
  const session = useSession(api);
  const { pathname } = useLocation();
  const [collapsed, setCollapsed] = useState(false);

  // 登录门变体：/chat 与 /interview 未登录时，渐变底衬由页壳承载并覆盖整个视口，
  // 侧栏导航与账号行隐去，登录面通栏居中。
  const gateRoute = isActive(pathname, "/chat") || isActive(pathname, "/interview");
  const gate = gateRoute && !session.isLoading && !session.isAuthenticated;
  // 对话页入口在右下角气泡，不再占侧栏导航项；/chat 自身与登录门态都不渲染（门态点气泡只会撞回同一扇门）。
  const onChatRoute = isActive(pathname, "/chat");
  const signedIn = session.isAuthenticated;

  return (
    <div className={[styles.shell, gate ? styles.shellGate : ""].join(" ")}>
      <aside
        className={[
          styles.sidebar,
          collapsed ? styles.sidebarCollapsed : "",
          gate ? styles.sidebarGate : "",
        ].join(" ")}
        aria-label="侧边栏"
      >
        <div className={styles.brandRow}>
          <Link className={styles.brandLink} to="/interview">
            <span className={styles.brandLogo} aria-hidden="true">
              <BrandMark className={styles.brandLogoMark} />
            </span>
            <h1 className={styles.brand}>better-resume</h1>
          </Link>
          <button
            type="button"
            className={styles.collapseToggle}
            onClick={() => {
              setCollapsed((previous) => !previous);
            }}
            aria-label={collapsed ? "展开侧边栏" : "收起侧边栏"}
            aria-expanded={!collapsed}
          >
            <PanelIcon />
          </button>
        </div>

        {gate ? null : (
          <div className={styles.sidebarBody}>
            <nav className={styles.nav} aria-label="主导航">
              {PRIMARY_NAV.map((item) => {
                const Icon = item.icon;
                const active = isActive(pathname, item.to);
                return (
                  <Link
                    key={item.to}
                    to={item.to}
                    className={[styles.navLink, active ? styles.navActive : ""].join(" ")}
                    aria-current={active ? "page" : undefined}
                  >
                    <Icon className={styles.navIcon} />
                    <span className={styles.navLabel}>{item.label}</span>
                  </Link>
                );
              })}
            </nav>

            <nav className={styles.navSecondary} aria-label="次级导航">
              {SECONDARY_NAV.map((item) => {
                const Icon = item.icon;
                const active = isActive(pathname, item.to);
                return (
                  <Link
                    key={item.to}
                    to={item.to}
                    className={[styles.navLink, active ? styles.navActive : ""].join(" ")}
                    aria-current={active ? "page" : undefined}
                  >
                    <Icon className={styles.navIcon} />
                    <span className={styles.navLabel}>{item.label}</span>
                    <ExternalIcon className={styles.navTrailing} />
                  </Link>
                );
              })}
            </nav>

            <div className={styles.account}>
              <span className={styles.avatar} aria-hidden="true">
                <UserIcon className={styles.avatarIcon} />
              </span>
              <span className={styles.accountName}>
                {signedIn && session.principal
                  ? `账号: ${session.principal.user_id}`
                  : "未登录"}
              </span>
              <Link
                className={styles.iconButton}
                to="/settings/ai"
                aria-label="AI 设置"
                title="AI 设置"
              >
                <GearIcon className={styles.iconButtonGlyph} />
              </Link>
              {signedIn ? (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    // Logout owns its own failure; only a rejection that escapes it reaches here.
                    api
                      .logout()
                      .then(() => queryClient.invalidateQueries())
                      .catch(() => undefined);
                  }}
                >
                  退出
                </Button>
              ) : null}
            </div>
          </div>
        )}
      </aside>

      <main className={styles.content}>{children}</main>

      {onChatRoute || gate ? null : (
        <Link className={styles.chatFab} to="/chat" aria-label="打开对话">
          <ChatIcon className={styles.chatFabIcon} />
        </Link>
      )}
    </div>
  );
}
