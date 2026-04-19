"""
chatbot/models.py
Pydantic models for request, response, session, and internal types.
"""
from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, timezone


def _now_utc():
    return datetime.now(timezone.utc)


# ── Request / Response ────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str                            # latest user message
    document: str = ""                      # current Markdown from the editor
    session_id: Optional[str] = None        # None → server creates one


class ResponseMetadata(BaseModel):
    session_id: str
    model: str
    command_parsed: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0
    retries: int = 0
    stages_used: list[str] = Field(default_factory=list)    # e.g. ["session", "commands", "prompt_builder", "tools", "llm"]
    tools_called: list[str] = Field(default_factory=list)   # e.g. ["word_count", "heading_extraction"]


class ChatResponse(BaseModel):
    reply: str
    metadata: ResponseMetadata


# ── Session ───────────────────────────────────────────────────────

class Turn(BaseModel):
    role: str       # "user" | "assistant" | "system" | "tool"
    content: str


class SessionState(BaseModel):
    session_id: str
    history: list[Turn] = Field(default_factory=list)
    execution_contexts: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_now_utc)
    last_active: datetime = Field(default_factory=_now_utc)


# ── Slash-command parsing ─────────────────────────────────────────

class ParsedCommand(BaseModel):
    name: Optional[str] = None      # e.g. "summarise", None if no command
    args: str = ""                   # everything after the /command
    original_text: str               # the raw user message