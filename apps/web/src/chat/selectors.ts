/** Merge rules between server history (Query) and local run state (store). */

import type { ChatMessageView } from "../api/types";
import type { ChatMessage } from "./store";

export function toLocalMessage(view: ChatMessageView): ChatMessage {
  return {
    key: view.client_message_id ?? `server:${view.seq}`,
    role: view.role === "user" ? "user" : "assistant",
    content: view.content,
    reasoning: view.reasoning ?? "",
    streaming: false,
    error: view.error_message ?? null,
    clientMessageId: view.client_message_id ?? null,
    seq: view.seq,
  };
}

/**
 * Server history is the source of truth; local messages are only kept while they are not
 * represented there yet.
 *
 * User turns dedupe exactly by client_message_id. An assistant draft dedupes by *the turn it
 * answers*: the server row that follows that user turn's persisted message. Anchoring on the turn
 * instead of the text is what stops two identical replies from swallowing each other (P8 /
 * web-04); comparing content survives only as a fallback for a draft with no user turn in front
 * of it (the page can merge a lone assistant message).
 */
export function mergeHistory(server: ChatMessageView[], local: ChatMessage[]): ChatMessage[] {
  const serverMessages = server.map(toLocalMessage);

  const persistedClientIds = new Set(
    serverMessages
      .map((message) => message.clientMessageId)
      .filter((value): value is string => Boolean(value)),
  );

  // Which user turns history already answers: the first assistant row after that turn's message.
  const answeredClientIds = new Set<string>();
  let serverTurn: string | null = null;
  for (const message of serverMessages) {
    if (message.role === "user") {
      serverTurn = message.clientMessageId;
    } else if (serverTurn) {
      answeredClientIds.add(serverTurn);
    }
  }

  const serverAssistantContent = new Set(
    serverMessages.filter((message) => message.role === "assistant").map((message) => message.content),
  );

  const pending: ChatMessage[] = [];
  let localTurn: string | null = null;
  for (const message of local) {
    if (message.role === "user") {
      localTurn = message.clientMessageId;
      if (!localTurn || !persistedClientIds.has(localTurn)) {
        pending.push(message); // optimistic turn the server has not stored yet
      }
      continue;
    }
    if (message.streaming) {
      pending.push(message);
      continue;
    }
    if (localTurn) {
      if (!answeredClientIds.has(localTurn)) {
        pending.push(message); // its turn is still unanswered on the server
      }
      continue;
    }
    if (!serverAssistantContent.has(message.content)) {
      pending.push(message);
    }
  }

  return [...serverMessages, ...pending];
}
