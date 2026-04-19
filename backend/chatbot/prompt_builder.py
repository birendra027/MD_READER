"""
chatbot/prompt_builder.py
Dynamically constructs the system prompt by composing prompt files
from the ``prompts/`` directory.

Prompt resolution order
-----------------------
1. ``prompts/system_main.md``          — base identity & behaviour rules
2. Session context block               — injected dynamically
3. ``prompts/commands/<cmd>.md``       — command-specific instructions (if any)
4. ``prompts/verification_enforcement.md`` — for /verify & /code modes
5. DOCUMENT CONTENT                    — the live Markdown from the editor

For code-first commands (/code, /verify) the DOCUMENT CONTENT is placed
*before* the task instructions so the model reads the code first.
"""
from __future__ import annotations
import asyncio
import logging
from pathlib import Path
from functools import lru_cache
from chatbot.models import ParsedCommand, SessionState
from chatbot import session as session_store

logger = logging.getLogger(__name__)

_PROMPTS_DIR: Path = Path(__file__).resolve().parent / "prompts"

# Commands where "read the code first" ordering matters
_CODE_FIRST_COMMANDS: set[str] = {"code", "verify", "run"}


@lru_cache(maxsize=64)
def _load_prompt(relative_path: str) -> str | None:
    """Load a prompt file relative to the ``prompts/`` directory.

    Returns ``None`` when the file does not exist so callers can
    gracefully skip optional sections.
    """
    full = _PROMPTS_DIR / relative_path
    if not full.is_file():
        logger.debug("Prompt file not found (skipped): %s", full)
        return None
    return full.read_text(encoding="utf-8")


def load_prompt(name: str) -> str:
    """Public helper — load a prompt by name.  Raises if missing."""
    text = _load_prompt(name)
    if text is None:
        raise FileNotFoundError(f"Prompt file not found: {_PROMPTS_DIR / name}")
    return text


def _build_document_section(document_content: str) -> str:
    doc = document_content.strip() if document_content else ""
    body = doc if doc else "*(empty — no content yet)*"
    return f"\n---\n## DOCUMENT CONTENT (current editor state)\n\n{body}\n---"


def build_system_prompt(
    command: ParsedCommand,
    document_content: str,
    session: SessionState,
    memory_context: str | None = None,
) -> str:
    """Build the full system message for the LLM."""

    # 1. Base prompt
    base = load_prompt("system_main.md")
    parts: list[str] = [base]

    # 1.5. Returning-user memory context
    if memory_context:
        parts.append(f"\n## RETURNING USER CONTEXT\n{memory_context}")

    # 2. Session context
    turn_count = len(session.history)
    if turn_count > 0:
        parts.append(
            f"\n## SESSION CONTEXT\n"
            f"This conversation has {turn_count} prior message(s). "
            f"The user may refer to earlier parts of the conversation."
        )

    # 3 & 4. For code-first commands: inject the document BEFORE the task
    is_code_first = command.name in _CODE_FIRST_COMMANDS
    doc_section = _build_document_section(document_content)

    if is_code_first:
        parts.append(doc_section)

    # 5. Command-specific instructions (loaded from prompts/commands/<cmd>.md)
    if command.name:
        cmd_prompt = _load_prompt(f"commands/{command.name}.md")
        if cmd_prompt:
            parts.append(f"\n## CURRENT TASK\n\n{cmd_prompt}")

    # 6. Verification enforcement for /verify and /code
    if is_code_first:
        verify_prompt = _load_prompt("verification_enforcement.md")
        if verify_prompt:
            parts.append(f"\n{verify_prompt}")

    # 7. For non-code-first commands: document goes at the end
    if not is_code_first:
        parts.append(doc_section)

    return "\n".join(parts)