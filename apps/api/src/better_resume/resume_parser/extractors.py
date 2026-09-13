"""Deterministic field extractors: contact, skills, projects (no LLM)."""

from __future__ import annotations

import re
from collections.abc import Sequence

from .models import Contact, Project
from .sections import DetectedSection, keyword_key

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?:\+?86[-\s]?)?1[3-9]\d{9}|\+\d{1,3}[-\s]?\d{6,12}")
URL_RE = re.compile(
    r"(?:https?://|www\.)[^\s，,;；、]+|(?:github|gitlab|linkedin)\.com/[^\s，,;；、]+"
)
NAME_LABEL_RE = re.compile(r"(?:姓名|名字|name)\s*[:：]\s*([^\s，,;；|]{2,20})", re.IGNORECASE)
SPLIT_RE = re.compile(r"[,，、;；/|·•\n\t]+|\s{2,}")
BULLET_RE = re.compile(r"^\s*(?:[-•·*]|\d+[.、)])\s*")
_TRAILING = " 。.;；,，、|"

_MAX_SKILL_LENGTH = 30
_MAX_NAME_LENGTH = 20
_MAX_PROJECT_TITLE_LENGTH = 40


def extract_contact(text: str) -> Contact:
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    name: str | None = None
    if labeled := NAME_LABEL_RE.search(text):
        name = labeled.group(1).strip()
    if not name:
        for line in lines:
            if _looks_like_contact_line(line) or keyword_key(line):
                continue
            name = line
            break

    return Contact(
        name=name,
        email=_first(EMAIL_RE, text),
        phone=_first(PHONE_RE, text),
        links=_dedupe(URL_RE.findall(text)),
    )


def extract_skills(text: str) -> list[str]:
    skills: list[str] = []
    seen: set[str] = set()

    for raw_line in text.splitlines():
        line = BULLET_RE.sub("", raw_line.strip())
        if not line:
            continue
        for piece in SPLIT_RE.split(line):
            skill = piece.strip(_TRAILING).strip()
            if not skill or len(skill) > _MAX_SKILL_LENGTH:
                continue
            if len(skill) < 2 and not skill.isalpha():
                continue
            marker = skill.lower()
            if marker in seen:
                continue
            seen.add(marker)
            skills.append(skill)
    return skills


def extract_projects(sections: Sequence[DetectedSection]) -> list[Project]:
    projects: list[Project] = []

    for section in sections:
        if section.key != "projects":
            continue
        current: Project | None = None
        for raw_line in section.text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if BULLET_RE.match(line):
                bullet = BULLET_RE.sub("", line).strip(_TRAILING)
                if current is None:
                    current = Project(name=section.title, highlights=[])
                    projects.append(current)
                if bullet:
                    current.highlights.append(bullet)
                continue
            if _is_project_title(line):
                current = Project(name=line, highlights=[])
                projects.append(current)
            elif current is not None:
                current.highlights.append(line.strip(_TRAILING))

    return projects


def _is_project_title(line: str) -> bool:
    return len(line) <= _MAX_PROJECT_TITLE_LENGTH and not line.endswith(
        ("。", ".", "；", ";", "，")
    )


def _looks_like_contact_line(line: str) -> bool:
    if EMAIL_RE.search(line) or PHONE_RE.search(line) or URL_RE.search(line):
        return True
    if len(line) > _MAX_NAME_LENGTH or any(char.isdigit() for char in line):
        return True
    return any(char in line for char in "：:@/|")


def _first(pattern: re.Pattern[str], text: str) -> str | None:
    match = pattern.search(text)
    return match.group(0) if match else None


def _dedupe(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result
