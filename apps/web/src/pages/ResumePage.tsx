import { useNavigate } from "react-router-dom";

import { Button } from "../components";
import styles from "./ResumePage.module.css";

/** 简历导入占位页的路由：简历库功能后置，两个导入入口都跳这里。 */
const IMPORT_TARGET = "/coming-soon/resume-import";

/** 导入图标：向上箭头 + 托盘，两个导入按钮共用。 */
function UploadIcon() {
  return (
    <svg
      className={styles.icon}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M12 15V4" />
      <path d="m7 9 5-5 5 5" />
      <path d="M5 15v3a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-3" />
    </svg>
  );
}

export function ResumePage() {
  const navigate = useNavigate();

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h2 className={styles.title}>我的简历</h2>
      </header>

      <div className={styles.toolbar}>
        <Button
          onClick={() => {
            Promise.resolve(navigate(IMPORT_TARGET)).catch(() => undefined);
          }}
        >
          <UploadIcon />
          导入简历 PDF
        </Button>
      </div>

      <div className={styles.emptyState}>
        <span className={styles.emptyIconWrap} aria-hidden="true">
          <svg
            className={styles.emptyIcon}
            viewBox="0 0 48 48"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.4"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M28 6H14a3 3 0 0 0-3 3v30a3 3 0 0 0 3 3h20a3 3 0 0 0 3-3V15z" />
            <path d="M28 6v9h9" />
            <path d="M19 27h10" />
            <path d="M19 34h6" />
          </svg>
        </span>
        <p className={styles.emptyTitle}>暂无简历文件</p>
        <Button
          onClick={() => {
            Promise.resolve(navigate(IMPORT_TARGET)).catch(() => undefined);
          }}
        >
          <UploadIcon />
          导入第一份简历
        </Button>
      </div>
    </div>
  );
}
