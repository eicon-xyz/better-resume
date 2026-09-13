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
