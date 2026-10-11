"""Skill-tag filtering over corpus entries (D23 / Q14).

Pure and offline: tags the resume already lists select reference questions, no vector store
and no network call. ASCII tags compare against whole skill tokens, so "Java" never reaches
JavaScript entries; CJK tags compare as substrings, so "容器化" still reaches Docker.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence

from .loader import CorpusEntry

#: How many reference questions reach one prompt unless the caller asks for another number.
DEFAULT_LIMIT = 24

_TOKEN_PATTERN = re.compile(r"[^0-9a-zA-Z+#]+")

#: topic (lower-cased) -> extra skill tags that should reach it.
TOPIC_ALIASES: dict[str, frozenset[str]] = {
    "python": frozenset({"python", "python3", "py"}),
    "java": frozenset({"java", "jdk", "jvm", "spring", "springboot", "mybatis"}),
    "javascript": frozenset(
        {"javascript", "js", "typescript", "ts", "node", "nodejs", "vue", "react", "reactjs"}
    ),
    "mysql": frozenset(
        {"mysql", "sql", "postgresql", "postgres", "sqlserver", "oracle", "数据库", "关系型数据库"}
    ),
    "redis": frozenset({"redis", "缓存", "cache"}),
    "kafka": frozenset({"kafka", "mq", "消息队列", "rocketmq", "rabbitmq"}),
    "http": frozenset({"http", "https", "tcp", "udp", "socket", "网络", "计算机网络", "协议"}),
    "操作系统": frozenset({"操作系统", "linux", "unix", "os", "内核", "进程", "线程"}),
    "算法": frozenset({"算法", "数据结构", "leetcode", "刷题", "algorithm"}),
    "docker": frozenset({"docker", "k8s", "kubernetes", "容器", "容器化"}),
}


def _aliases_for(topic: str) -> frozenset[str]:
    normalized = topic.strip().lower()
    return TOPIC_ALIASES.get(normalized, frozenset({normalized}))


def skill_tokens(skills: Iterable[str]) -> set[str]:
    """Skill strings broken into whole alphanumeric tokens (case-insensitive)."""
    tokens: set[str] = set()
    for skill in skills:
        for token in _TOKEN_PATTERN.split(skill):
            cleaned = token.strip().lower()
            if cleaned:
                tokens.add(cleaned)
    return tokens


def _topic_matches(topic: str, tokens: set[str], haystack: str) -> bool:
    for alias in _aliases_for(topic):
        if alias.isascii():
            if alias in tokens:
                return True
        elif alias in haystack:
            return True
    return False


def filter_corpus(
    entries: Sequence[CorpusEntry], skills: Iterable[str], *, limit: int = DEFAULT_LIMIT
) -> list[CorpusEntry]:
    """Entries whose topic is reachable from the resume skills, capped at limit, file order."""
    if limit <= 0:
        return []
    skill_list = list(skills)
    tokens = skill_tokens(skill_list)
    haystack = " ".join(skill_list).lower()
    return [entry for entry in entries if _topic_matches(entry.topic, tokens, haystack)][:limit]


__all__ = ["DEFAULT_LIMIT", "TOPIC_ALIASES", "filter_corpus", "skill_tokens"]
