import type { components, paths } from "./schema";

/** Wire types, generated from the backend OpenAPI document (D17). */
export type Schemas = components["schemas"];

export type Principal = Schemas["Principal"];
export type ChatSessionView = Schemas["ChatSessionView"];
export type ChatMessageView = Schemas["ChatMessageView"];
export type ModelView = Schemas["ModelView"];
export type ChatSessionCreateRequest = Schemas["ChatSessionCreateRequest"];
export type ChatSessionUpdateRequest = Schemas["SessionUpdateRequest"];
export type ChatStreamRequest = Schemas["StreamRequest"];
export type AuthSessionRequest = Schemas["AuthSessionRequest"];

export type ChatStreamPath = paths["/api/v1/chat/sessions/{session_id}/stream"];
// ---- interview (M2) ----
export type InterviewSessionView = Schemas["InterviewSessionView"];
export type InterviewSessionCreateRequest = Schemas["InterviewSessionCreateRequest"];
export type GeneratedQuestionView = Schemas["GeneratedQuestionView"];
export type QuestionBatchView = Schemas["QuestionBatchView"];
export type AnswerView = Schemas["AnswerView"];
export type AnswerSubmitRequest = Schemas["AnswerSubmitRequest"];
export type AnswerSubmitView = Schemas["AnswerSubmitView"];
export type FlowView = Schemas["FlowView"];
export type RestoreResponseView = Schemas["RestoreResponseView"];
export type InterviewReportView = Schemas["InterviewReportView"];
export type DimensionView = Schemas["DimensionView"];
export type ReportTurnView = Schemas["ReportTurnView"];

/** M4 media contracts (generated names are re-exported for readability). */
export type WsTicketView = components["schemas"]["WsTicketView"];
export type TtsRequestView = components["schemas"]["TtsRequest"];
export type TtsView = components["schemas"]["TtsView"];
