import { useNavigate, useParams } from "react-router-dom";

import { Button } from "../components";
import styles from "./PlaceholderPage.module.css";

/** 未上线功能的 slug → 中文名。未知 slug 回落到「该功能」。 */
const FEATURE_LABELS: Record<string, string> = {
  "interview-assist": "面试辅助",
  "knowledge-base": "定制知识库",
  "user-manual": "用户手册",
  "whats-new": "最新更新",
  "resume-import": "导入简历",
};

/** 占位页：导航里已列出的未上线功能统一落到这里，只报名称与状态，不做任何假交互。 */
export function PlaceholderPage() {
  const { slug } = useParams();
  const navigate = useNavigate();
  const label = FEATURE_LABELS[slug ?? ""] ?? "该功能";

  return (
    <section className={styles.page} aria-labelledby="placeholder-title">
      <p className={styles.badge}>敬请期待</p>
      <h2 className={styles.title} id="placeholder-title">
        {label}
      </h2>
      <p className={styles.description}>该功能尚未上线，上线后会在这里开放入口。</p>
      <Button
        variant="secondary"
        onClick={() => {
          Promise.resolve(navigate("/interview")).catch(() => undefined);
        }}
      >
        返回模拟面试
      </Button>
    </section>
  );
}
