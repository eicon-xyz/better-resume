"""Conversation module errors; ownership failures collapse into not-found (no existence leak)."""

from __future__ import annotations


class ConversationError(Exception):
    """Base class for conversation module failures."""


class ConversationNotFoundError(ConversationError):
    """Raised when a conversation does not exist, is not owned by the user, or has another kind."""


class ConversationConflictError(ConversationError):
    """Raised when a concurrent write violates the per-conversation sequence invariant."""
