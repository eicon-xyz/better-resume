/** Interview server state (TanStack Query): session list + report snapshots. */

import { useQuery } from "@tanstack/react-query";
import type { UseQueryResult } from "@tanstack/react-query";

import type { ApiClient } from "../api/client";
import type { InterviewReportView, InterviewSessionView } from "../api/types";
import { DEFAULT_AUTH_EPOCH } from "../chat/queries";

export const interviewKeys = {
  all: (authEpoch: string) => ["interview", authEpoch] as const,
  sessions: (authEpoch: string) => [...interviewKeys.all(authEpoch), "sessions"] as const,
  report: (authEpoch: string, sessionId: string) =>
    [...interviewKeys.all(authEpoch), "report", sessionId] as const,
};

export function useInterviewSessions(
  client: ApiClient,
  enabled = true,
  authEpoch: string = DEFAULT_AUTH_EPOCH,
): UseQueryResult<InterviewSessionView[]> {
  return useQuery({
    queryKey: interviewKeys.sessions(authEpoch),
    queryFn: () => client.listInterviewSessions(),
    enabled,
  });
}

export function useInterviewReport(
  client: ApiClient,
  sessionId: string | null,
  enabled = true,
  authEpoch: string = DEFAULT_AUTH_EPOCH,
): UseQueryResult<InterviewReportView> {
  return useQuery({
    queryKey: interviewKeys.report(authEpoch, sessionId ?? "none"),
    queryFn: () => client.getInterviewReport(sessionId ?? ""),
    enabled: enabled && Boolean(sessionId),
  });
}
