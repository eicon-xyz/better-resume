/** Resume upload controller: validation, preview, progress and the create→upload handshake. */

import { useCallback, useEffect, useRef, useState } from "react";

import type { ApiClient, UploadOptions } from "../api/client";
import { ApiError } from "../api/errors";
import type { InterviewSessionView, QuestionBatchView } from "../api/types";

export const MAX_RESUME_BYTES = 10 * 1024 * 1024;
const PDF_MAGIC = "%PDF-";

export type UploadStage = "idle" | "uploading" | "generating" | "ready" | "error";

export interface ResumeUploadState {
  file: File | null;
  previewUrl: string | null;
  progress: number;
  stage: UploadStage;
  error: string | null;
  session: InterviewSessionView | null;
  batch: QuestionBatchView | null;
}

export interface UseResumeUploadOptions {
  client: ApiClient;
  onQuestionsReady?: (sessionId: string, batch: QuestionBatchView) => void;
  uploadOptions?: Pick<UploadOptions, "xhrFactory">;
}

export interface ResumeUploadController extends ResumeUploadState {
  selectFile(file: File | null): Promise<void>;
  start(): Promise<void>;
  reset(): void;
}

export function validateResumeFile(file: File, head: string): string | null {
  if (file.size === 0) return "文件是空的";
  if (file.size > MAX_RESUME_BYTES) return "文件过大（上限 10MB）";
  const looksPdf = file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");
  if (!looksPdf) return "只支持 PDF 文件";
  if (!head.startsWith(PDF_MAGIC)) return "这个文件不是有效的 PDF（可能是扫描件或改过后缀）";
  return null;
}

async function readHead(file: File, length = 5): Promise<string> {
  const buffer = await file.slice(0, length).arrayBuffer();
  return new TextDecoder().decode(buffer);
}

export function useResumeUpload({
  client,
  onQuestionsReady,
  uploadOptions,
}: UseResumeUploadOptions): ResumeUploadController {
  const [state, setState] = useState<ResumeUploadState>({
    file: null,
    previewUrl: null,
    progress: 0,
    stage: "idle",
    error: null,
    session: null,
    batch: null,
  });
  const previewRef = useRef<string | null>(null);

  useEffect(() => {
    return () => {
      if (previewRef.current) URL.revokeObjectURL(previewRef.current);
    };
  }, []);

  const selectFile = useCallback(async (file: File | null) => {
    if (previewRef.current) {
      URL.revokeObjectURL(previewRef.current);
      previewRef.current = null;
    }
    if (file === null) {
      setState((current) => ({ ...current, file: null, previewUrl: null, stage: "idle", error: null }));
      return;
    }

    const problem = validateResumeFile(file, await readHead(file));
    if (problem) {
      setState((current) => ({ ...current, file: null, previewUrl: null, stage: "error", error: problem }));
      return;
    }

    const url = URL.createObjectURL(file);
    previewRef.current = url;
    setState((current) => ({
      ...current,
      file,
      previewUrl: url,
      stage: "idle",
      error: null,
      progress: 0,
    }));
  }, []);

  const start = useCallback(async () => {
    const file = state.file;
    if (!file) return;

    setState((current) => ({ ...current, stage: "uploading", error: null, progress: 0 }));
    try {
      const session = await client.createInterviewSession({});
      setState((current) => ({ ...current, session, stage: "generating" }));
      const batch = await client.uploadResumeAndGenerateQuestions(session.id, file, {
        onProgress: (ratio) =>
          setState((current) => ({ ...current, progress: Math.min(1, Math.max(0, ratio)) })),
        ...uploadOptions,
      });
      setState((current) => ({ ...current, batch, stage: "ready", progress: 1 }));
      onQuestionsReady?.(session.id, batch);
    } catch (error) {
      const message =
        error instanceof ApiError ? error.message : "出题失败，请稍后重试";
      setState((current) => ({ ...current, stage: "error", error: message }));
    }
  }, [client, onQuestionsReady, state.file, uploadOptions]);

  const reset = useCallback(() => {
    if (previewRef.current) {
      URL.revokeObjectURL(previewRef.current);
      previewRef.current = null;
    }
    setState({
      file: null,
      previewUrl: null,
      progress: 0,
      stage: "idle",
      error: null,
      session: null,
      batch: null,
    });
  }, []);

  return { ...state, selectFile, start, reset };
}
