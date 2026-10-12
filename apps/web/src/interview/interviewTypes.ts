/** The upload page's controlled interview focus; mirrors the backend InterviewType enum. */

export interface InterviewTypeOption {
  value: string;
  label: string;
}

export const INTERVIEW_TYPE_OPTIONS: InterviewTypeOption[] = [
  { value: "auto", label: "自动（按简历）" },
  { value: "fundamentals", label: "八股基础" },
  { value: "project", label: "项目深挖" },
  { value: "internship", label: "实习深挖" },
];

export function interviewTypeLabel(value: string | null | undefined): string {
  return INTERVIEW_TYPE_OPTIONS.find((option) => option.value === value)?.label ?? "模拟面试";
}
