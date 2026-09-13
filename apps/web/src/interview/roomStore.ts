/** Interview room run state (zustand). Server truth stays in Query; this is one session's UI state. */

import { create } from "zustand";

import type { AnswerSubmitView, GeneratedQuestionView, RestoreResponseView } from "../api/types";

export interface InterviewTurn {
  questionNo: string;
  kind: "main" | "follow_up";
  question: string;
  focusPoints: string[];
  answer: string | null;
  score: number | null;
  feedback: string | null;
  missingPoints: string[];
  followUpReason: string | null;
  pending: boolean;
}

export interface RoomState {
  sessionId: string | null;
  sessionStatus: string;
  flowStatus: string;
  currentQuestion: GeneratedQuestionView | null;
  turns: InterviewTurn[];
  answered: number;
  totalQuestions: number;
  submitting: boolean;
  error: string | null;

  hydrate(sessionId: string, view: RestoreResponseView): void;
  askQuestion(question: GeneratedQuestionView | null): void;
  submitStart(questionNo: string, answer: string): void;
  applyTurnResult(result: AnswerSubmitView): void;
  failSubmit(message: string): void;
  reset(): void;
}

const EMPTY = {
  sessionId: null,
  sessionStatus: "unknown",
  flowStatus: "init",
  currentQuestion: null,
  turns: [] as InterviewTurn[],
  answered: 0,
  totalQuestions: 0,
  submitting: false,
  error: null,
};

function toTurn(question: GeneratedQuestionView): InterviewTurn {
  return {
    questionNo: question.question_no,
    kind: question.kind === "follow_up" ? "follow_up" : "main",
    question: question.text,
    focusPoints: question.focus_points ?? [],
    answer: null,
    score: null,
    feedback: null,
    missingPoints: [],
    followUpReason: null,
    pending: true,
  };
}

export const useRoomStore = create<RoomState>((set) => ({
  ...EMPTY,

  hydrate: (sessionId, view) => {
    const answered = view.answered ?? 0;
    set({
      ...EMPTY,
      sessionId,
      sessionStatus: view.session.status,
      flowStatus: view.flow.status,
      currentQuestion: view.current_question ?? null,
      totalQuestions: view.total_questions ?? view.flow.total_questions ?? 0,
      answered,
      turns: view.current_question ? [toTurn(view.current_question)] : [],
    });
  },

  askQuestion: (question) => {
    set((state) => ({
      currentQuestion: question,
      turns:
        question === null || state.turns.some((turn) => turn.questionNo === question.question_no)
          ? state.turns
          : [...state.turns, toTurn(question)],
    }));
  },

  submitStart: (questionNo, answer) => {
    set((state) => ({
      submitting: true,
      error: null,
      turns: state.turns.map((turn) =>
        turn.questionNo === questionNo ? { ...turn, answer, pending: true } : turn,
      ),
    }));
  },

  applyTurnResult: (result) => {
    set((state) => {
      const answeredTurn = result.answer;
      const turns = state.turns.map((turn) =>
        turn.questionNo === answeredTurn.question_no
          ? {
              ...turn,
              answer: turn.answer,
              score: answeredTurn.score ?? null,
              feedback: answeredTurn.feedback ?? null,
              missingPoints: answeredTurn.missing_points ?? [],
              followUpReason: answeredTurn.follow_up_reason ?? null,
              pending: false,
            }
          : turn,
      );
      const next = result.next_question ?? null;
      return {
        turns:
          next && !turns.some((turn) => turn.questionNo === next.question_no)
            ? [
                ...turns,
                {
                  ...toTurn(next),
                  // The reason lives on the answer that triggered this question.
                  followUpReason: answeredTurn.follow_up_reason ?? null,
                },
              ]
            : turns,
        currentQuestion: next,
        sessionStatus: result.session.status,
        flowStatus: result.flow.status,
        answered: state.answered + 1,
        submitting: false,
        error: null,
      };
    });
  },

  failSubmit: (message) => {
    set((state) => ({
      submitting: false,
      error: message,
      turns: state.turns.map((turn) => (turn.pending ? { ...turn, pending: false } : turn)),
    }));
  },

  reset: () => {
    set({ ...EMPTY });
  },
}));
