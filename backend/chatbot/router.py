"""
chatbot/router.py
FastAPI router — SSE streaming endpoint + legacy fallback + code execution.
"""
from __future__ import annotations
import asyncio
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel, Field
from chatbot.models import ChatRequest, ChatResponse, ResponseMetadata
from chatbot.lifecycle import run_turn
from chatbot import session as session_store
from chatbot.tools import (
    dispatch_tool, install_packages, detect_missing_packages,
    scan_imports, check_installed,
    _ensure_sandbox, _OUTPUT_DIR, _EXEC_TIMEOUT,
)
from chatbot.llm_client import fix_code
import s3_client

log = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chatbot"])

# ── Per-session output directory ──────────────────────────────────
_SESSION_RE = re.compile(r"^[a-fA-F0-9\-]{1,64}$")


def _session_output_dir(session_id: str) -> Path:
    """Return (and create) a session-specific output directory."""
    if not session_id or not _SESSION_RE.match(session_id):
        return _OUTPUT_DIR
    d = _OUTPUT_DIR / session_id
    d.mkdir(parents=True, exist_ok=True)
    return d


_INTERNAL_OUTPUT_PATH_RE = re.compile(
    r"(?:[A-Za-z]:)?(?:[\\/][^\s`\"']*)*(?:app[\\/]backend[\\/]output|backend[\\/]output)(?:[\\/][^\s`\"']+)*",
    re.IGNORECASE,
)


def _sanitize_execution_text(text: str) -> str:
    """Hide internal output paths before storing runtime context."""
    def repl(match: re.Match[str]) -> str:
        raw = match.group(0)
        parts = [p for p in re.split(r"[\\/]+", raw) if p]
        last = parts[-1] if parts else ""
        if "." in last:
            return f'generated file "{last}"'
        return "Generated Files folder"

    return _INTERNAL_OUTPUT_PATH_RE.sub(repl, text)


def _compact_execution_excerpt(result: "_ExecResult") -> str:
    """Build a concise, useful runtime excerpt for later chat turns."""
    combined = []
    if result.stdout.strip():
        combined.append(result.stdout.strip())
    if result.stderr.strip():
        combined.append(result.stderr.strip())
    text = _sanitize_execution_text("\n".join(combined)).strip()
    if not text:
        return "(no runtime output)"
    lines = [line for line in text.splitlines() if line.strip()]
    lines = lines[-40:]
    excerpt = "\n".join(lines)
    return excerpt[-3000:]


def _build_execution_context_note(
    language: str,
    code: str,
    result: "_ExecResult",
    auto_installed: list[str],
    was_fixed: bool,
) -> str:
    """Create hidden session context for a completed code execution."""
    status = "succeeded" if result.exit_code == 0 else "failed"
    files = ", ".join(result.files) if result.files else "none"
    note = [
        f"Execution result ({language}): {status}.",
        f"Exit code: {result.exit_code}",
        f"Auto-installed packages: {', '.join(auto_installed) if auto_installed else 'none'}",
        f"Code was auto-fixed: {'yes' if was_fixed else 'no'}",
        f"Generated files: {files}",
        "Relevant runtime output:",
        _compact_execution_excerpt(result),
    ]
    if result.exit_code != 0:
        note.append(
            "If the user asks what the error means, explain this specific runtime failure directly rather than asking them to provide the error again."
        )
    return "\n".join(note)


async def _persist_execution_context(
    session_id: str,
    language: str,
    code: str,
    result: "_ExecResult",
    auto_installed: list[str],
    was_fixed: bool,
) -> None:
    """Save hidden execution context so later chat turns can reference it."""
    if not session_id:
        return
    note = _build_execution_context_note(language, code, result, auto_installed, was_fixed)
    await session_store.append_execution_context(session_id, note)


# ── Session persistence endpoints ─────────────────────────────────

class DisconnectRequest(BaseModel):
    session_id: str


@router.post("/disconnect")
async def disconnect(req: DisconnectRequest):
    """Called when the browser tab is closing. Save session to disk."""
    from chatbot.session import save_all_sessions
    await save_all_sessions()
    return {"status": "saved"}


class HistoryResponse(BaseModel):
    session_id: str
    messages: list[dict] = Field(default_factory=list)


@router.get("/history/{session_id}", response_model=HistoryResponse)
async def get_chat_history(session_id: str):
    """Restore chat history for a returning user."""
    sess = await session_store.get_or_create(session_id)
    history = await session_store.get_history(sess.session_id)
    return HistoryResponse(session_id=sess.session_id, messages=history)


# ── Execute code endpoint ─────────────────────────────────────────

class ExecuteRequest(BaseModel):
    code: str
    language: str = "python"    # "python" | "shell"
    session_id: str = ""        # isolate output per user session


class ExecuteResponse(BaseModel):
    exit_code: int = -1
    stdout: str = ""
    stderr: str = ""
    error: str = ""
    output_dir: str = ""
    files: list[str] = Field(default_factory=list)
    missing_packages: list[str] = Field(default_factory=list)
    auto_installed: list[str] = Field(default_factory=list)
    retried: bool = False


_MAX_AUTO_RETRIES = 2


@router.post("/execute", response_model=ExecuteResponse)
async def execute_code(req: ExecuteRequest):
    """
    Execute a code snippet directly.
    If the first run fails with ModuleNotFoundError, auto-install the missing
    packages and re-execute (up to _MAX_AUTO_RETRIES times) so the user sees
    the real output instead of an import error.
    """
    loop = asyncio.get_event_loop()
    all_installed: list[str] = []

    for attempt in range(_MAX_AUTO_RETRIES + 1):
        if req.language in ("python", "py"):
            raw = await loop.run_in_executor(
                None, dispatch_tool, "execute_python", {"code": req.code}, ""
            )
        elif req.language in ("shell", "bash", "sh", "powershell", "pwsh", "cmd"):
            raw = await loop.run_in_executor(
                None, dispatch_tool, "execute_shell", {"command": req.code}, ""
            )
        else:
            return ExecuteResponse(error=f"Unsupported language: {req.language}")

        result = json.loads(raw)

        if "error" in result and "missing_packages" not in result:
            return ExecuteResponse(
                error=result["error"],
                output_dir=result.get("output_dir", ""),
                auto_installed=all_installed,
                retried=bool(all_installed),
            )

        missing = result.get("missing_packages", [])

        # If execution succeeded or no missing packages, return now
        if result.get("exit_code", -1) == 0 or not missing:
            return ExecuteResponse(
                exit_code=result.get("exit_code", -1),
                stdout=result.get("stdout", ""),
                stderr=result.get("stderr", ""),
                output_dir=result.get("output_dir", ""),
                files=result.get("files_in_output", []),
                missing_packages=missing,
                auto_installed=all_installed,
                retried=bool(all_installed),
            )

        # Still have retries left — install missing packages and retry
        if attempt < _MAX_AUTO_RETRIES:
            install_result = await loop.run_in_executor(
                None, install_packages, missing
            )
            if install_result.get("exit_code") == 0:
                all_installed.extend(missing)
            else:
                # Install failed — return the original execution error
                return ExecuteResponse(
                    exit_code=result.get("exit_code", -1),
                    stdout=result.get("stdout", ""),
                    stderr=result.get("stderr", "")
                        + f"\n\n--- pip install failed ---\n"
                        + install_result.get("stderr", ""),
                    output_dir=result.get("output_dir", ""),
                    files=result.get("files_in_output", []),
                    missing_packages=missing,
                    auto_installed=all_installed,
                    retried=bool(all_installed),
                )

    # Exhausted retries — return last result
    return ExecuteResponse(
        exit_code=result.get("exit_code", -1),
        stdout=result.get("stdout", ""),
        stderr=result.get("stderr", ""),
        output_dir=result.get("output_dir", ""),
        files=result.get("files_in_output", []),
        missing_packages=result.get("missing_packages", []),
        auto_installed=all_installed,
        retried=bool(all_installed),
    )


# ── Install packages endpoint ─────────────────────────────────────

class InstallRequest(BaseModel):
    packages: list[str]


class InstallResponse(BaseModel):
    exit_code: int = -1
    stdout: str = ""
    stderr: str = ""
    error: str = ""
    installed: list[str] = Field(default_factory=list)


@router.post("/install", response_model=InstallResponse)
async def install_pkgs(req: InstallRequest):
    """Install pip packages after user approval."""
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, install_packages, req.packages)
    if "error" in result:
        return InstallResponse(error=result["error"])
    return InstallResponse(
        exit_code=result.get("exit_code", -1),
        stdout=result.get("stdout", ""),
        stderr=result.get("stderr", ""),
        installed=result.get("installed", []),
    )


# ── Auto-fix endpoint ────────────────────────────────────────────

class AutoFixRequest(BaseModel):
    code: str
    language: str = "python"
    error: str  # stderr or error message from the failed run


class AutoFixStep(BaseModel):
    attempt: int
    stage: str  # "installing", "fixing", "running", "success", "failed"
    detail: str = ""
    code: str = ""


class AutoFixResponse(BaseModel):
    success: bool = False
    fixed_code: str = ""
    exit_code: int = -1
    stdout: str = ""
    stderr: str = ""
    attempts: int = 0
    auto_installed: list[str] = Field(default_factory=list)
    steps: list[AutoFixStep] = Field(default_factory=list)


_MAX_FIX_RETRIES = 3


@router.post("/auto-fix", response_model=AutoFixResponse)
async def auto_fix(req: AutoFixRequest):
    """
    Automatically investigate and fix failed code.

    1. Check for missing packages → install & retry
    2. Send error to LLM → get fixed code → execute
    3. Repeat until success or max retries exhausted
    """
    loop = asyncio.get_event_loop()
    current_code = req.code
    current_error = req.error
    all_installed: list[str] = []
    steps: list[dict] = []

    # Resolve the correct tool based on language
    lang = req.language.lower()
    is_shell = lang in ("shell", "bash", "sh", "powershell", "pwsh", "cmd")
    tool_name = "execute_shell" if is_shell else "execute_python"
    tool_key = "command" if is_shell else "code"

    async def _run(code: str):
        return await loop.run_in_executor(
            None, dispatch_tool, tool_name, {tool_key: code}, ""
        )

    for attempt in range(1, _MAX_FIX_RETRIES + 1):
        # ── Step 1: Check for missing packages (Python only) ──
        if not is_shell:
            from chatbot.tools import detect_missing_packages
            missing = detect_missing_packages(current_error)
            if missing:
                steps.append({"attempt": attempt, "stage": "installing",
                              "detail": f"Installing: {', '.join(missing)}"})
                install_result = await loop.run_in_executor(None, install_packages, missing)
                if install_result.get("exit_code") == 0:
                    all_installed.extend(missing)
                    steps.append({"attempt": attempt, "stage": "running",
                                  "detail": "Re-running after package install…"})
                    raw = await _run(current_code)
                    result = json.loads(raw)
                    if result.get("exit_code", -1) == 0:
                        steps.append({"attempt": attempt, "stage": "success",
                                      "detail": "Code succeeded after installing packages ✅"})
                        return AutoFixResponse(
                            success=True, fixed_code=current_code,
                            exit_code=0, stdout=result.get("stdout", ""),
                            stderr=result.get("stderr", ""),
                            attempts=attempt, auto_installed=all_installed, steps=steps,
                        )
                    current_error = result.get("stderr", "") or str(result.get("error", ""))

        # ── Step 2: Ask LLM to fix the code ──
        steps.append({"attempt": attempt, "stage": "fixing",
                      "detail": f"Investigating error (attempt {attempt})…"})
        fixed = await fix_code(current_code, current_error, req.language)
        if not fixed:
            steps.append({"attempt": attempt, "stage": "failed",
                          "detail": "Could not generate a fix"})
            break

        current_code = fixed

        # ── Step 3: Execute the fixed code ──
        steps.append({"attempt": attempt, "stage": "running",
                      "detail": f"Running fixed code (attempt {attempt})…",
                      "code": current_code})
        raw = await _run(current_code)
        result = json.loads(raw)

        # Check for missing packages in fixed code too (Python only)
        if not is_shell:
            new_missing = result.get("missing_packages", [])
            if new_missing:
                install_result = await loop.run_in_executor(None, install_packages, new_missing)
                if install_result.get("exit_code") == 0:
                    all_installed.extend(new_missing)
                    raw = await _run(current_code)
                    result = json.loads(raw)

        if result.get("exit_code", -1) == 0:
            steps.append({"attempt": attempt, "stage": "success",
                          "detail": f"Code fixed & succeeded on attempt {attempt} ✅"})
            return AutoFixResponse(
                success=True, fixed_code=current_code,
                exit_code=0, stdout=result.get("stdout", ""),
                stderr=result.get("stderr", ""),
                attempts=attempt, auto_installed=all_installed, steps=steps,
            )

        # Update error for next iteration
        current_error = result.get("stderr", "") or str(result.get("error", ""))
        steps.append({"attempt": attempt, "stage": "failed",
                      "detail": f"Still failing (attempt {attempt})"})

    # Exhausted retries
    last_result = result if 'result' in locals() else {}
    return AutoFixResponse(
        success=False, fixed_code=current_code,
        exit_code=last_result.get("exit_code", -1),
        stdout=last_result.get("stdout", ""),
        stderr=current_error,
        attempts=_MAX_FIX_RETRIES, auto_installed=all_installed, steps=steps,
    )


# ── Streaming execution (real-time output) ────────────────────────

_SHELL_LANGS = frozenset(("shell", "bash", "sh", "powershell", "pwsh", "cmd"))
_PYTHON_LANGS = frozenset(("python", "py"))
_MAX_STREAM_LINES = 500


def _sse(event: str, data) -> str:
    """Format a single Server-Sent Event."""
    payload = json.dumps(data, ensure_ascii=False) if not isinstance(data, str) else data
    return f"event: {event}\ndata: {payload}\n\n"


class _ExecResult:
    """Mutable container to capture subprocess results alongside streaming."""
    __slots__ = ("exit_code", "stdout", "stderr", "missing_packages", "files")

    def __init__(self):
        self.exit_code: int = -1
        self.stdout: str = ""
        self.stderr: str = ""
        self.missing_packages: list[str] = []
        self.files: list[str] = []


def _upload_output_to_s3(out_dir: Path, filenames: list[str], session_id: str) -> None:
    """Upload execution output files to S3 (best-effort, called in thread)."""
    for name in filenames:
        local = out_dir / name
        if local.is_file():
            key = s3_client._output_key(session_id, name)
            s3_client.upload_file(key, local)


async def _stream_subprocess(code: str, language: str, result: _ExecResult, output_dir: Path | None = None, session_id: str = ""):
    """Run code in a subprocess and yield SSE output events line by line.

    Uses ``subprocess.Popen`` with background reader threads + an
    ``asyncio.Queue`` to stream output without blocking the event loop.
    This avoids the Windows ``SelectorEventLoop`` limitation where
    ``asyncio.create_subprocess_exec`` is not supported.
    """
    out_dir = output_dir or _OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    lang = language.lower()
    is_python = lang in _PYTHON_LANGS

    if lang in _SHELL_LANGS:
        blocked = ["rm -rf /", "mkfs", "dd if=", ":(){", "fork bomb",
                    "format c:", "del /s /q c:\\"]
        lower_cmd = code.lower()
        for b in blocked:
            if b in lower_cmd:
                yield _sse("error", {"detail": f"Blocked dangerous command: {b}"})
                return

    tmp_path: str | None = None
    proc = None
    try:
        env = {**os.environ, "OUTPUT_DIR": str(out_dir)}
        loop = asyncio.get_event_loop()

        if is_python:
            sandbox_py = str(await loop.run_in_executor(None, _ensure_sandbox))
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".py", delete=False, encoding="utf-8",
            ) as f:
                f.write(code)
                tmp_path = f.name
            cmd = [sandbox_py, "-u", tmp_path]
        elif sys.platform == "win32":
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".ps1", delete=False, encoding="utf-8",
            ) as f:
                f.write("$ErrorActionPreference = 'Stop'\n")
                f.write(code)
                tmp_path = f.name
            cmd = ["powershell", "-ExecutionPolicy", "Bypass",
                   "-NoProfile", "-File", tmp_path]
        else:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".sh", delete=False, encoding="utf-8",
            ) as f:
                f.write(code)
                tmp_path = f.name
            cmd = ["bash", tmp_path]

        log.info("_stream_subprocess: starting %s", cmd[0])
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(out_dir),
            env=env,
        )

        # Thread-safe queue bridging blocking reads → async generator
        queue: asyncio.Queue[tuple[str, str | None]] = asyncio.Queue()

        def _reader(stream, name: str):
            """Read lines from a blocking pipe and push to the async queue."""
            try:
                for raw_line in iter(stream.readline, b""):
                    text = raw_line.decode("utf-8", errors="replace")
                    loop.call_soon_threadsafe(queue.put_nowait, (name, text))
            except Exception:
                pass
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, (name, None))

        t_out = threading.Thread(target=_reader, args=(proc.stdout, "stdout"), daemon=True)
        t_err = threading.Thread(target=_reader, args=(proc.stderr, "stderr"), daemon=True)
        t_out.start()
        t_err.start()

        stdout_parts: list[str] = []
        stderr_parts: list[str] = []
        done_streams = 0
        timed_out = False
        line_count = 0

        while done_streams < 2:
            try:
                name, text = await asyncio.wait_for(queue.get(), timeout=_EXEC_TIMEOUT)
            except asyncio.TimeoutError:
                proc.kill()
                timed_out = True
                break

            if text is None:
                done_streams += 1
                continue

            if name == "stdout":
                stdout_parts.append(text)
            else:
                stderr_parts.append(text)

            line_count += 1
            if line_count <= _MAX_STREAM_LINES:
                yield _sse("output", {"stream": name, "text": text})
            elif line_count == _MAX_STREAM_LINES + 1:
                yield _sse("output", {
                    "stream": "stderr",
                    "text": f"\n… output truncated ({line_count}+ lines) …\n",
                })

        t_out.join(timeout=5)
        t_err.join(timeout=5)

        if timed_out:
            yield _sse("output", {
                "stream": "stderr",
                "text": f"\n⏱ Timed out after {_EXEC_TIMEOUT // 60} min.\n",
            })
            result.exit_code = -1
        else:
            result.exit_code = proc.wait()

        result.stdout = "".join(stdout_parts)[-8000:]
        result.stderr = "".join(stderr_parts)[-4000:]
        result.missing_packages = (
            detect_missing_packages(result.stderr)
            if is_python and result.exit_code != 0 else []
        )
        result.files = sorted(
            str(p.name) for p in out_dir.iterdir() if p.is_file()
        )
        # Upload any new files to S3 (best-effort, non-blocking)
        if result.exit_code == 0 and result.files and session_id:
            _upload_output_to_s3(out_dir, result.files, session_id)
        log.info("_stream_subprocess: exit_code=%d lines=%d", result.exit_code, line_count)

    except Exception as e:
        log.exception("_stream_subprocess failed")
        yield _sse("error", {"detail": str(e) or repr(e)})
        result.exit_code = -1
    finally:
        if proc and proc.poll() is None:
            proc.kill()
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass


@router.post("/execute-stream")
async def execute_stream(req: ExecuteRequest):
    """Stream real-time code execution output + auto-fix progress via SSE."""

    sess = await session_store.get_or_create(req.session_id or None)
    effective_session_id = sess.session_id

    # Resolve session-specific output directory
    out_dir = _session_output_dir(effective_session_id)

    async def generate():
        lang = req.language.lower()
        is_python = lang in _PYTHON_LANGS
        is_shell = lang in _SHELL_LANGS

        if not is_python and not is_shell:
            yield _sse("error", {"detail": f"Unsupported language: {req.language}"})
            yield _sse("done", "[DONE]")
            return

        current_code = req.code
        all_installed: list[str] = []
        was_fixed = False

        # ── Phase 0: Pre-scan imports & install missing packages ──
        if is_python:
            yield _sse("status", {"stage": "scanning", "detail": "Checking dependencies…"})
            loop = asyncio.get_event_loop()
            needed = await loop.run_in_executor(None, scan_imports, current_code)
            if needed:
                missing = await loop.run_in_executor(None, check_installed, needed)
                if missing:
                    yield _sse("status", {
                        "stage": "installing",
                        "detail": f"📦 Installing: {', '.join(missing)}…",
                    })
                    yield _sse("output", {
                        "stream": "stdout",
                        "text": f"📦 Auto-installing: {', '.join(missing)}…\n",
                    })
                    inst = await loop.run_in_executor(None, install_packages, missing)
                    if inst.get("exit_code") == 0:
                        all_installed.extend(missing)
                        yield _sse("output", {
                            "stream": "stdout",
                            "text": f"✅ Installed: {', '.join(missing)}\n"
                                    + "─" * 36 + "\n",
                        })
                    else:
                        yield _sse("output", {
                            "stream": "stderr",
                            "text": f"⚠️ Install failed: {inst.get('stderr', '')[:500]}\n"
                                    + "─" * 36 + "\n",
                        })

        # ── Phase 1: Initial execution ──
        yield _sse("status", {"stage": "running", "detail": "Executing code…"})
        result = _ExecResult()
        async for chunk in _stream_subprocess(current_code, req.language, result, output_dir=out_dir, session_id=effective_session_id):
            yield chunk

        if result.exit_code == 0:
            await _persist_execution_context(effective_session_id, req.language, current_code, result, all_installed, False)
            yield _sse("result", {
                "success": True, "exit_code": 0, "was_fixed": False,
                "fixed_code": "", "auto_installed": all_installed,
                "files": result.files, "session_id": effective_session_id,
            })
            yield _sse("done", "[DONE]")
            return

        # ── Phase 2: Auto-install from stderr if still missing (Python only) ──
        if is_python and result.missing_packages:
            for _ in range(_MAX_AUTO_RETRIES):
                pkgs = result.missing_packages
                yield _sse("status", {
                    "stage": "installing",
                    "detail": f"📦 Installing: {', '.join(pkgs)}…",
                })
                loop = asyncio.get_event_loop()
                inst = await loop.run_in_executor(None, install_packages, pkgs)
                if inst.get("exit_code") != 0:
                    yield _sse("output", {
                        "stream": "stderr",
                        "text": f"Install failed: {inst.get('stderr', '')}\n",
                    })
                    break
                all_installed.extend(pkgs)
                yield _sse("status", {
                    "stage": "running",
                    "detail": "🔄 Re-running after install…",
                })
                result = _ExecResult()
                async for chunk in _stream_subprocess(
                    current_code, req.language, result, output_dir=out_dir, session_id=effective_session_id,
                ):
                    yield chunk
                if result.exit_code == 0 or not result.missing_packages:
                    break

        if result.exit_code == 0:
            await _persist_execution_context(effective_session_id, req.language, current_code, result, all_installed, False)
            yield _sse("result", {
                "success": True, "exit_code": 0, "was_fixed": False,
                "fixed_code": "", "auto_installed": all_installed,
                "files": result.files, "session_id": effective_session_id,
            })
            yield _sse("done", "[DONE]")
            return

        # ── Phase 3: Auto-fix loop ──
        current_error = result.stderr or result.stdout

        for attempt in range(1, _MAX_FIX_RETRIES + 1):
            # Check for missing packages first
            if is_python:
                missing = detect_missing_packages(current_error)
                if missing:
                    yield _sse("status", {
                        "stage": "installing",
                        "detail": f"📦 Installing: {', '.join(missing)}…",
                    })
                    inst = await asyncio.get_event_loop().run_in_executor(
                        None, install_packages, missing,
                    )
                    if inst.get("exit_code") == 0:
                        all_installed.extend(missing)
                        yield _sse("status", {
                            "stage": "running",
                            "detail": "Re-running after install…",
                        })
                        result = _ExecResult()
                        async for chunk in _stream_subprocess(
                            current_code, req.language, result, output_dir=out_dir, session_id=effective_session_id,
                        ):
                            yield chunk
                        if result.exit_code == 0:
                            await _persist_execution_context(effective_session_id, req.language, current_code, result, all_installed, was_fixed)
                            yield _sse("result", {
                                "success": True, "exit_code": 0,
                                "was_fixed": was_fixed,
                                "fixed_code": current_code if was_fixed else "",
                                "auto_installed": all_installed,
                                "files": result.files, "session_id": effective_session_id,
                            })
                            yield _sse("done", "[DONE]")
                            return
                        current_error = result.stderr or result.stdout

            # Ask LLM to fix
            yield _sse("status", {
                "stage": "investigating",
                "detail": f"🔍 Investigating error (attempt {attempt}/{_MAX_FIX_RETRIES})…",
            })

            fixed = await fix_code(current_code, current_error, req.language)
            if not fixed:
                yield _sse("status", {
                    "stage": "fix_failed",
                    "detail": "Could not generate a fix",
                })
                break

            current_code = fixed
            was_fixed = True
            yield _sse("fix_code", {"attempt": attempt, "code": current_code})
            yield _sse("status", {
                "stage": "running",
                "detail": f"▶ Running fixed code (attempt {attempt})…",
            })

            result = _ExecResult()
            async for chunk in _stream_subprocess(
                current_code, req.language, result, output_dir=out_dir, session_id=effective_session_id,
            ):
                yield chunk

            # Auto-install for fixed code too
            if is_python and result.missing_packages:
                inst = await asyncio.get_event_loop().run_in_executor(
                    None, install_packages, result.missing_packages,
                )
                if inst.get("exit_code") == 0:
                    all_installed.extend(result.missing_packages)
                    result = _ExecResult()
                    async for chunk in _stream_subprocess(
                        current_code, req.language, result, output_dir=out_dir, session_id=effective_session_id,
                    ):
                        yield chunk

            if result.exit_code == 0:
                await _persist_execution_context(effective_session_id, req.language, current_code, result, all_installed, True)
                yield _sse("result", {
                    "success": True, "exit_code": 0, "was_fixed": True,
                    "fixed_code": current_code,
                    "auto_installed": all_installed, "files": result.files,
                    "session_id": effective_session_id,
                })
                yield _sse("done", "[DONE]")
                return

            current_error = result.stderr or result.stdout
            yield _sse("status", {
                "stage": "fix_failed",
                "detail": f"❌ Still failing (attempt {attempt})",
            })

        # Exhausted retries
        await _persist_execution_context(effective_session_id, req.language, current_code, result, all_installed, was_fixed)
        yield _sse("result", {
            "success": False, "exit_code": result.exit_code,
            "was_fixed": was_fixed,
            "fixed_code": current_code if was_fixed else "",
            "auto_installed": all_installed, "files": result.files,
            "session_id": effective_session_id,
        })
        yield _sse("done", "[DONE]")

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── SSE streaming endpoint ────────────────────────────────────────

@router.post("/stream")
async def chat_stream(req: ChatRequest, request: Request):
    """
    Stream LLM tokens as Server-Sent Events.

    Client should send:
      - JSON body: { message, document, session_id? }

    Server streams:
      data: <token>
      event: metadata  data: { session_id, model, ... }
      event: done      data: [DONE]
    """
    # Honour X-Session-ID header as fallback
    if not req.session_id:
        req.session_id = request.headers.get("X-Session-ID")

    async def generate():
        async for chunk in run_turn(req):
            yield chunk

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── Legacy non-streaming endpoint (kept for backward compat) ──────

@router.post("", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest, request: Request):
    """Non-streaming fallback — collects full response then returns JSON."""
    if not req.session_id:
        req.session_id = request.headers.get("X-Session-ID")

    full_reply = ""
    metadata = None

    async for chunk in run_turn(req):
        if chunk.startswith("event: metadata"):
            # Parse metadata from the SSE line
            import json
            data_line = chunk.split("data: ", 1)[1].split("\n")[0]
            metadata = ResponseMetadata.model_validate_json(data_line)
        elif chunk.startswith("event: done"):
            continue
        elif chunk.startswith("data: "):
            # Extract text from SSE data line
            text = chunk[6:].rstrip("\n\n").replace("\ndata: ", "\n")
            full_reply += text

    if not metadata:
        metadata = ResponseMetadata(
            session_id=req.session_id or "",
            model="unknown",
        )

    return ChatResponse(reply=full_reply, metadata=metadata)


# ── File listing & download (session-scoped, backed by S3) ───────

@router.get("/files/{session_id}")
async def list_session_files(session_id: str):
    """Return all files generated by this session, with S3 pre-signed download URLs."""
    if not _SESSION_RE.match(session_id):
        return {"files": []}
    loop = asyncio.get_event_loop()
    items = await loop.run_in_executor(None, s3_client.list_session_files, session_id)
    # Attach a pre-signed URL to each file so the browser can download directly
    for item in items:
        item["url"] = await loop.run_in_executor(
            None, s3_client.presigned_url, item["key"], 3600
        )
    return {"files": items}


@router.get("/files/{session_id}/{filename}/url")
async def get_file_url(session_id: str, filename: str):
    """Return a fresh pre-signed URL for a specific session file."""
    if not _SESSION_RE.match(session_id):
        return {"error": "Invalid session"}
    safe_name = Path(filename).name
    key = s3_client._output_key(session_id, safe_name)
    loop = asyncio.get_event_loop()
    url = await loop.run_in_executor(None, s3_client.presigned_url, key, 3600)
    if not url:
        return {"error": "File not found or S3 unavailable"}
    return {"url": url, "filename": safe_name, "expires_in": 3600}


@router.get("/files/{session_id}/{filename}")
async def download_session_file(session_id: str, filename: str):
    """Redirect to S3 pre-signed URL; fall back to local file if S3 is unavailable."""
    from fastapi.responses import RedirectResponse
    if not _SESSION_RE.match(session_id):
        return {"error": "Invalid session"}
    safe_name = Path(filename).name
    key = s3_client._output_key(session_id, safe_name)
    loop = asyncio.get_event_loop()
    url = await loop.run_in_executor(None, s3_client.presigned_url, key, 3600)
    if url:
        return RedirectResponse(url, status_code=302)
    # Fallback: serve directly from local filesystem
    filepath = _OUTPUT_DIR / session_id / safe_name
    if filepath.is_file() and filepath.resolve().is_relative_to((_OUTPUT_DIR / session_id).resolve()):
        return FileResponse(filepath, filename=safe_name)
    return {"error": "File not found"}