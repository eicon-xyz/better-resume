/** Human wording for the generation-time signals the backend reports (never silent). */

const DEGRADED_MESSAGES: Record<string, string> = {
  resume_unparsable:
    "简历没有解析出可用的文本层，本轮改为通用八股题；换一份可复制的 PDF 可以重试。",
  corpus_no_match: "本次没有匹配到八股语料，题目全部由模型生成。",
};

const WARNING_MESSAGES: Record<string, string> = {
  no_sections_detected: "简历里没有识别出章节标题，题目会更依赖模型判断。",
  no_contact_found: "简历里没有找到联系方式。",
  no_skills_found: "简历里没有提取到技能标签，八股语料无法匹配。",
};

export function degradedNotices(reasons: string[] | null | undefined): string[] {
  const codes = reasons ?? [];
  if (codes.length === 0) return [];
  const known = codes
    .map((code) => DEGRADED_MESSAGES[code])
    .filter((message): message is string => Boolean(message));
  return known.length > 0 ? known : ["本次出题已降级，部分参考数据不可用。"];
}

export function degradedNotice(reasons: string[] | null | undefined): string | null {
  const notices = degradedNotices(reasons);
  return notices.length > 0 ? notices.join(" ") : null;
}

/** The deterministic parser's quality warnings, worded for the candidate. */
export function resumeWarningNotices(warnings: string[] | null | undefined): string[] {
  return (warnings ?? []).map((code) => WARNING_MESSAGES[code] ?? "解析提示：" + code);
}
