"""Bundled fundamentals corpus: reference questions shipped with the package (D23)."""

from .loader import CORPUS_FILENAME, DEFAULT_CORPUS_PATH, CorpusEntry, CorpusError, load_corpus
from .matching import DEFAULT_LIMIT, filter_corpus

__all__ = [
    "CORPUS_FILENAME",
    "DEFAULT_CORPUS_PATH",
    "DEFAULT_LIMIT",
    "CorpusEntry",
    "CorpusError",
    "filter_corpus",
    "load_corpus",
]
