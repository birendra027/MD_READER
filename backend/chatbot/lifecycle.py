"""
chatbot/lifecycle.py
Orchestrates the full lifecycle of a conversational turn:

1. Resolve / create session
2. Parse slash commands
3. Short-circuit client commands (/clear, /help, /export)
4. Build system prompt
5. Invoke LLM with tools + streaming
6. Collect metadata (model, tokens, latency, retries)
7. Persist assistant turn to session
8. Yield tokens + final metadata event via SSE
"""

from __future__ import annotations
import time
import logging
from typing import AsyncGenerator
from chatbot.models import ChatRequest, ParsedCommand, ResponseMetadata
from chatbot.commands import parse as parse_command, CLIENT_COMMANDS, HELP_TEXT
from chatbot.prompt_builder import build_system_prompt
from chatbot.llm_client import stream_chat, MODEL, TokenUsage, ToolProgress
from chatbot import session

logger = logging.getLogger(__name__)


async def run_turn(request: ChatRequest) -> AsyncGenerator[str, None]:
    """
    Execute a single conversational turn.

    Yields SSE-formatted strings:
        data: <token>      - streamed LLM tokens
        event: metadata    - structured result JSON
        event: done        - signals end of stream
    """
    start = time.perf_counter()
    stages_used: list[str] = []

    # — 1. Session
    sess = await session.get_or_create(request.session_id)
    session_id = sess.session_id
    stages_used.append("session")
    logger.info("— TURN START — session=%s, history=%d turns", session_id[:8], len(sess.history))

    # — 2. Parse command
    cmd: ParsedCommand = parse_command(request.message)
    stages_used.append("commands")
    logger.info("📂 commands.parse -> command=%s, args=%r", cmd.name or "(none)", cmd.args)

    # — 3. Short-circuit client commands
    if cmd.name in CLIENT_COMMANDS:
        stages_used.append(f"client_cmd:{cmd.name}")
        logger.info("⚡ Short-circuit client command: %s", cmd.name)
        reply = await _handle_client_command(cmd, request.document, session_id)
        await session.append_turn(session_id, "user", request.message)
        await session.append_turn(session_id, "assistant", reply)

        latency = int((time.perf_counter() - start) * 1000)
        yield _sse_data(reply)
        yield _sse_metadata(ResponseMetadata(
            session_id=session_id,
            model="local",
            command_parsed=cmd.name,
            latency_ms=latency,
            stages_used=stages_used,
        ))
        yield _sse_done()
        logger.info("— TURN END — %dms, stages=%s", latency, stages_used)
        return

    # — 4. Build system prompt (with returning-user memory if available)
    memory_context = await session.get_session_summary(session_id)
    system_prompt = build_system_prompt(cmd, request.document, sess, memory_context=memory_context)
    stages_used.append("prompt_builder")
    if memory_context:
        stages_used.append("memory_recall")
    logger.info("🧠 prompt_builder -> prompt length=%d chars%s", len(system_prompt),
                " (with memory)" if memory_context else "")

    # — 5. Build messages list
    history = await session.get_history(session_id)
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history)

    if cmd.name:
        user_content = cmd.args if cmd.args else f"/{cmd.name}"
    else:
        user_content = request.message
    messages.append({"role": "user", "content": user_content})

    await session.append_turn(session_id, "user", request.message)
    logger.info("💬 Messages built: %d total (%d history + system + user)", len(messages), len(history))

    # — 6. Invoke LLM with streaming
    stages_used.append("llm")
    full_reply = ""
    token_usage = None
    try:
        async for item in stream_chat(messages, document=request.document):
            if isinstance(item, TokenUsage):
                token_usage = item
                if item.tools_called:
                    stages_used.append("tools")
            elif isinstance(item, ToolProgress):
                yield _sse_thinking(item.stage, item.detail, item.tool_name)
            else:
                full_reply += item
                yield _sse_data(item)
    except Exception as e:
        logger.exception("LLM call failed")
        error_msg = f"⚠️ Error: {str(e)}"
        yield _sse_data(error_msg)
        full_reply = error_msg

    # — 7. Persist assistant turn
    await session.append_turn(session_id, "assistant", full_reply)
    stages_used.append("session_persist")

    # — 8. Metadata event
    latency = int((time.perf_counter() - start) * 1000)
    tools_called = token_usage.tools_called if token_usage else []
    logger.info(
        "— TURN END — %dms, tokens=%d+%d, tools=%s, stages=%s",
        latency,
        token_usage.input_tokens if token_usage else 0,
        token_usage.output_tokens if token_usage else 0,
        tools_called or "(none)",
        stages_used,
    )

    yield _sse_metadata(ResponseMetadata(
        session_id=session_id,
        model=MODEL,
        command_parsed=cmd.name,
        input_tokens=token_usage.input_tokens if token_usage else 0,
        output_tokens=token_usage.output_tokens if token_usage else 0,
        latency_ms=latency,
        stages_used=stages_used,
        tools_called=tools_called,
    ))
    yield _sse_done()

    # — Client-command handlers 
    
async def _handle_client_command(
    cmd: ParsedCommand, document: str, session_id: str
) -> str:
    if cmd.name == "clear":
        await session.clear_session(session_id)
        return "🗑️ Conversation cleared."
    elif cmd.name == "help":
        return HELP_TEXT
    elif cmd.name == "export":
        if document.strip():
            return f"```markdown\n{document}\n```"
        return "The document is empty – nothing to export."
    return "Unknown command."


# — SSE formatting helpers

def _sse_data(text: str) -> str:
    """Standard SSE data line.

    Each logical data payload is sent as **one** `data:` line.
    Newlines inside the text are encoded as literal `\\n` so the
    frontend can decode them back into real newlines without the SSE
    parser splitting them into separate events.
    """
    safe = text.replace("\\", "\\\\").replace("\n", "\\n")
    return f"data: {safe}\n\n"


def _sse_thinking(stage: str, detail: str, tool_name: str | None = None) -> str:
    """SSE event that signals thinking / tool-call progress to the frontend."""
    import json as _json
    payload = {"stage": stage, "detail": detail}
    if tool_name:
        payload["tool"] = tool_name
    return f"event: thinking\ndata: {_json.dumps(payload)}\n\n"


def _sse_metadata(meta: ResponseMetadata) -> str:
    return f"event: metadata\ndata: {meta.model_dump_json()}\n\n"


def _sse_done() -> str:
    return "event: done\ndata: [DONE]\n\n"