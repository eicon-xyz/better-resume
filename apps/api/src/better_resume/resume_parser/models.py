"""ResumeContext: the Pydantic contract produced by deterministic parsing (D10)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Contact(BaseModel):
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    links: list[str] = Field(default_factory=list)


class Section(BaseModel):
    title: str
    bullets: list[str] = Field(default_factory=list)


class Project(BaseModel):
    name: str
    description: str | None = None
    highlights: list[str] = Field(default_factory=list)


class ResumeContext(BaseModel):
    contact: Contact = Field(default_factory=Contact)
    sections: list[Section] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)
