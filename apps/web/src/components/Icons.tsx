import type { SVGProps } from "react";

/** 页壳内联图标集：统一取 currentColor 与 --br-size-icon，不引任何外部图标资源。
    线稿图标一律带 .br-icon 基础类，调用方 className 与之合并（默认尺寸来自基础类，
    需要别的尺寸时由调用方类覆盖）；品牌标记用 accent 底色 + contrast 前景的实心图形。 */

type IconProps = SVGProps<SVGSVGElement>;

function LineIcon({ children, className, ...rest }: IconProps) {
  return (
    <svg
      className={["br-icon", className].filter(Boolean).join(" ")}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...rest}
    >
      {children}
    </svg>
  );
}

export function CalendarIcon(props: IconProps) {
  return (
    <LineIcon {...props}>
      <rect x="3" y="5" width="18" height="16" rx="3" />
      <path d="M3 10h18M8 3v4M16 3v4" />
      <path d="m9 15 2 2 4-4" />
    </LineIcon>
  );
}

export function BookIcon(props: IconProps) {
  return (
    <LineIcon {...props}>
      <path d="M5 4.5A1.5 1.5 0 0 1 6.5 3H18a1 1 0 0 1 1 1v13.5H7A2 2 0 0 0 5 19.5z" />
      <path d="M5 19.5A2.5 2.5 0 0 0 7.5 21H19v-3.5" />
      <path d="M9 8h6" />
    </LineIcon>
  );
}

export function TargetIcon(props: IconProps) {
  return (
    <LineIcon {...props}>
      <circle cx="12" cy="12" r="8.5" />
      <path d="m8.5 12 2.5 2.5 4.5-5" />
    </LineIcon>
  );
}

export function UserIcon(props: IconProps) {
  return (
    <LineIcon {...props}>
      <circle cx="12" cy="8" r="3.6" />
      <path d="M5 20.5c0-3.6 3.1-5.5 7-5.5s7 1.9 7 5.5" />
    </LineIcon>
  );
}

export function QuestionIcon(props: IconProps) {
  return (
    <LineIcon {...props}>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M9.6 9.5a2.5 2.5 0 1 1 3.1 2.4c-.7.3-1.1.9-1.1 1.6v.3" />
      <path d="M11.6 17h.8" />
    </LineIcon>
  );
}

export function SparkIcon(props: IconProps) {
  return (
    <LineIcon {...props}>
      <path d="m12 3 1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z" />
      <path d="M18.5 16.5 19 18l1.5.5-1.5.5-.5 1.5-.5-1.5L16 18.5l1.5-.5z" />
    </LineIcon>
  );
}

export function ExternalIcon(props: IconProps) {
  return (
    <LineIcon {...props}>
      <path d="M14 4h6v6" />
      <path d="M20 4 11 13" />
      <path d="M18 15v3.5A1.5 1.5 0 0 1 16.5 20h-10A1.5 1.5 0 0 1 5 18.5v-10A1.5 1.5 0 0 1 6.5 7H10" />
    </LineIcon>
  );
}

export function GearIcon(props: IconProps) {
  return (
    <LineIcon {...props}>
      <circle cx="12" cy="12" r="3.2" />
      <path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.9.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.9 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.9l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.9.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.9-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.9V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z" />
    </LineIcon>
  );
}

export function ChatIcon(props: IconProps) {
  return (
    <LineIcon {...props}>
      <path d="M20.5 11.5a7.5 7.5 0 0 1-7.5 7.5H11l-4.5 3v-3.6A7.5 7.5 0 0 1 12.5 4h.5a7.5 7.5 0 0 1 7.5 7.5z" />
    </LineIcon>
  );
}

export function PanelIcon(props: IconProps) {
  return (
    <LineIcon {...props}>
      <rect x="3.5" y="4.5" width="17" height="15" rx="3" />
      <path d="M9.5 4.5v15" />
    </LineIcon>
  );
}

/** 品牌标记：暖黄圆角方块内嵌对话气泡 + 播放三角，不抄任何外部素材。 */
export function BrandMark(props: IconProps) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" {...props}>
      <path
        d="M20 11.2c0 3.6-3.6 6.5-8 6.5-.9 0-1.8-.1-2.6-.3l-4 2.4.9-4.1c-1.4-1.2-2.3-2.8-2.3-4.5 0-3.6 3.6-6.5 8-6.5s8 2.9 8 6.5z"
        fill="var(--br-color-accent-contrast)"
      />
      <path d="m9.4 8.6 5.4 2.6-5.4 2.6z" fill="var(--br-color-accent)" />
    </svg>
  );
}
