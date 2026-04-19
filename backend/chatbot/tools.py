"""
chatbot/tools.py
Tool definitions for OpenAI function-calling and their Python handlers.
These tools let the LLM perform concrete operations on the document.
"""
from __future__ import annotations
import json
import logging
import re
import subprocess
import sys
import tempfile
import os
from pathlib import Path
from typing import Callable

log = logging.getLogger(__name__)

# The Python interpreter that is running THIS backend process.
_PYTHON_BIN = sys.executable

# The *real* system Python (outside any venv).  On Windows, creating a venv
# from inside another venv crashes ensurepip, so we always use the base
# interpreter for sandbox creation.
_BASE_PYTHON = getattr(sys, "_base_executable", sys.executable)

# ── Sandbox virtual-environment for user code execution ───────────
# Completely isolated from the backend venv so that pip-installing
# packages for user scripts never pollutes the app environment or
# triggers uvicorn reload storms.

_SANDBOX_DIR = Path(__file__).resolve().parent.parent.parent / "sandbox_venv"

if sys.platform == "win32":
    _SANDBOX_PYTHON = _SANDBOX_DIR / "Scripts" / "python.exe"
else:
    _SANDBOX_PYTHON = _SANDBOX_DIR / "bin" / "python"


def _ensure_sandbox() -> Path:
    """Create the sandbox venv if it doesn't already exist.
    Uses the *base* system Python so ensurepip doesn't crash on Windows.
    Returns the path to the sandbox Python interpreter."""
    if _SANDBOX_PYTHON.exists():
        return _SANDBOX_PYTHON
    log.info("Creating sandbox venv at %s (using %s) …", _SANDBOX_DIR, _BASE_PYTHON)

    # Step 1: create the venv WITHOUT pip (this never fails)
    proc = subprocess.run(
        [_BASE_PYTHON, "-m", "venv", "--without-pip", str(_SANDBOX_DIR)],
        capture_output=True, text=True, timeout=120,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"Failed to create sandbox venv (exit {proc.returncode}): {proc.stderr}"
        )

    # Step 2: bootstrap pip inside the sandbox using the base Python's ensurepip
    sandbox_py = str(_SANDBOX_PYTHON)
    proc = subprocess.run(
        [sandbox_py, "-c",
         "import ensurepip; ensurepip._main(['--upgrade', '--default-pip'])"],
        capture_output=True, text=True, timeout=120,
    )
    if proc.returncode != 0:
        # Fallback: try pip from the backend venv to install pip into sandbox
        log.warning("ensurepip failed, trying pip bootstrap fallback …")
        subprocess.run(
            [_PYTHON_BIN, "-m", "pip", "install", "--target",
             str(_SANDBOX_DIR / "Lib" / "site-packages" if sys.platform == "win32"
                 else _SANDBOX_DIR / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "site-packages"),
             "pip"],
            capture_output=True, text=True, timeout=120,
        )

    if not _SANDBOX_PYTHON.exists():
        raise RuntimeError(f"Sandbox python not found at {_SANDBOX_PYTHON}")
    log.info("Sandbox venv ready.")
    return _SANDBOX_PYTHON

# ── Tool handlers ─────────────────────────────────────────────────

def _word_count(document: str, **_) -> str:
    count = len(document.split()) if document.strip() else 0
    return json.dumps({"word_count": count})


def _char_count(document: str, **_) -> str:
    return json.dumps({"char_count": len(document)})


def _heading_extraction(document: str, **_) -> str:
    headings = re.findall(r"^(#{1,6})\s+(.+)$", document, re.MULTILINE)
    result = [{"level": len(h[0]), "text": h[1].strip()} for h in headings]
    return json.dumps({"headings": result})


def _search_document(document: str, query: str = "", **_) -> str:
    if not query:
        return json.dumps({"matches": [], "note": "No query provided"})
    lines = document.splitlines()
    matches = [
        {"line": i + 1, "text": line.strip()}
        for i, line in enumerate(lines)
        if query.lower() in line.lower()
    ]
    return json.dumps({"query": query, "matches": matches})


def _extract_code_blocks(document: str, **_) -> str:
    """Extract all fenced code blocks from the document."""
    pattern = re.compile(r"```(\w*)\n(.*?)```", re.DOTALL)
    blocks = []
    for i, m in enumerate(pattern.finditer(document), start=1):
        lang = m.group(1) or "plain"
        code = m.group(2).rstrip("\n")
        # Find the line number of this block
        line_no = document[:m.start()].count("\n") + 1
        blocks.append({
            "index": i,
            "language": lang,
            "line": line_no,
            "code": code,
            "length_lines": code.count("\n") + 1,
        })
    return json.dumps({
        "total_code_blocks": len(blocks),
        "code_blocks": blocks,
    })


def _extract_todos(document: str, **_) -> str:
    """Extract TODO items, checkboxes, and action markers from the document."""
    todos: list[dict] = []

    for i, line in enumerate(document.splitlines(), start=1):
        stripped = line.strip()

        # Markdown checkboxes
        if re.match(r"^-\s*\[x]\s+", stripped, re.IGNORECASE):
            todos.append({"line": i, "text": stripped, "type": "done", "category": "checkbox"})
        elif re.match(r"^-\s*\[\s?]\s+", stripped):
            todos.append({"line": i, "text": stripped, "type": "pending", "category": "checkbox"})

        # TODO / FIXME / HACK / XXX markers
        marker_match = re.search(r"\b(TODO|FIXME|HACK|XXX):\s*(.*)", stripped, re.IGNORECASE)
        if marker_match:
            todos.append({
                "line": i,
                "text": marker_match.group(0),
                "type": "pending",
                "category": marker_match.group(1).upper(),
            })

    done = sum(1 for t in todos if t["type"] == "done")
    pending = sum(1 for t in todos if t["type"] == "pending")
    total = done + pending
    pct = round((done / total) * 100) if total > 0 else 0

    return json.dumps({
        "total": total,
        "done": done,
        "pending": pending,
        "progress_pct": pct,
        "items": todos,
    })


# ── Script execution ──────────────────────────────────────────────

_EXEC_TIMEOUT = 600  # 10 minutes

# Persistent output directory for generated files (Excel, CSV, images, etc.)
_OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"
_OUTPUT_DIR.mkdir(exist_ok=True)


def _execute_python(document: str, code: str = "", **_) -> str:
    """Execute a Python script in a subprocess and return stdout/stderr.

    • Working directory is ``backend/output/`` so any files the script
      creates (Excel, CSV, images …) land there.
    • The env-var ``OUTPUT_DIR`` is also set so scripts can reference it.
    • Timeout is 10 minutes.  On timeout the whole process tree is killed.
    """
    if not code.strip():
        return json.dumps({"error": "No code provided to execute."})

    sandbox_py = str(_ensure_sandbox())
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(code)
            tmp_path = f.name

        env = {**os.environ, "OUTPUT_DIR": str(_OUTPUT_DIR)}
        proc = subprocess.Popen(
            [sandbox_py, "-u", tmp_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=str(_OUTPUT_DIR),
            env=env,
        )
        try:
            stdout, stderr = proc.communicate(timeout=_EXEC_TIMEOUT)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            return json.dumps({
                "error": f"Execution timed out after {_EXEC_TIMEOUT // 60} minutes.",
                "output_dir": str(_OUTPUT_DIR),
            })

        # List any files that were created/modified in output/
        created = sorted(str(p.name) for p in _OUTPUT_DIR.iterdir() if p.is_file())

        # Detect missing modules for the frontend install prompt
        missing = detect_missing_packages(stderr) if proc.returncode != 0 else []

        result_dict = {
            "exit_code": proc.returncode,
            "stdout": stdout[-8000:] if stdout else "",
            "stderr": stderr[-4000:] if stderr else "",
            "output_dir": str(_OUTPUT_DIR),
            "files_in_output": created,
        }
        if missing:
            result_dict["missing_packages"] = missing

        return json.dumps(result_dict)
    except Exception as e:
        return json.dumps({"error": str(e)})
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass


def _execute_shell(document: str, command: str = "", **_) -> str:
    """Execute a shell command and return stdout/stderr.

    On Windows, commands are executed via PowerShell for better
    compatibility (cmd.exe cannot handle bash-style syntax at all).
    """
    if not command.strip():
        return json.dumps({"error": "No command provided to execute."})
    # Block dangerous commands
    blocked = ["rm -rf /", "mkfs", "dd if=", ":(){", "fork bomb",
               "format c:", "del /s /q c:\\"]
    lower_cmd = command.lower()
    for b in blocked:
        if b in lower_cmd:
            return json.dumps({"error": f"Blocked dangerous command pattern: {b}"})

    tmp_path = None
    try:
        env = {**os.environ, "OUTPUT_DIR": str(_OUTPUT_DIR)}

        if sys.platform == "win32":
            # Write to a temp .ps1 file and execute with PowerShell
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".ps1", delete=False, encoding="utf-8"
            ) as f:
                # Set strict error handling so failures produce non-zero exit
                f.write("$ErrorActionPreference = 'Stop'\n")
                f.write(command)
                tmp_path = f.name

            proc = subprocess.Popen(
                ["powershell", "-ExecutionPolicy", "Bypass",
                 "-NoProfile", "-File", tmp_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=str(_OUTPUT_DIR),
                env=env,
            )
        else:
            proc = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=str(_OUTPUT_DIR),
                env=env,
            )

        try:
            stdout, stderr = proc.communicate(timeout=_EXEC_TIMEOUT)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            return json.dumps({
                "error": f"Execution timed out after {_EXEC_TIMEOUT // 60} minutes.",
                "output_dir": str(_OUTPUT_DIR),
            })

        created = sorted(str(p.name) for p in _OUTPUT_DIR.iterdir() if p.is_file())

        return json.dumps({
            "exit_code": proc.returncode,
            "stdout": stdout[-8000:] if stdout else "",
            "stderr": stderr[-4000:] if stderr else "",
            "output_dir": str(_OUTPUT_DIR),
            "files_in_output": created,
        })
    except Exception as e:
        return json.dumps({"error": str(e)})
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass


# ── Missing-module detection & package installation ───────────────

_MODULE_ERROR_RE = re.compile(
    r"(?:ModuleNotFoundError|ImportError):\s*No module named ['\"]?(\w[\w.]*)['\"]?",
)

# Also detect "not installed" style messages from stdout (when code catches its own errors)
_STDOUT_MISSING_RE = re.compile(
    r"(?:is not installed|No module named|ModuleNotFoundError|ImportError).*?['\"]?(\w[\w.]*)['\"]?",
    re.IGNORECASE,
)

# Common module-name → pip-package-name mappings
_PIP_NAME_MAP: dict[str, str] = {
    "cv2": "opencv-python",
    "sklearn": "scikit-learn",
    "yaml": "pyyaml",
    "PIL": "Pillow",
    "bs4": "beautifulsoup4",
    "dateutil": "python-dateutil",
    "dotenv": "python-dotenv",
    "gi": "PyGObject",
    "attr": "attrs",
    "serial": "pyserial",
    "usb": "pyusb",
    "wx": "wxPython",
}

# Standard-library modules that should never be pip-installed
_STDLIB_MODULES: frozenset[str] = frozenset({
    "abc", "aifc", "argparse", "array", "ast", "asynchat", "asyncio",
    "asyncore", "atexit", "audioop", "base64", "bdb", "binascii",
    "binhex", "bisect", "builtins", "bz2", "calendar", "cgi", "cgitb",
    "chunk", "cmath", "cmd", "code", "codecs", "codeop", "collections",
    "colorsys", "compileall", "concurrent", "configparser", "contextlib",
    "contextvars", "copy", "copyreg", "cProfile", "crypt", "csv",
    "ctypes", "curses", "dataclasses", "datetime", "dbm", "decimal",
    "difflib", "dis", "distutils", "doctest", "email", "encodings",
    "enum", "errno", "faulthandler", "fcntl", "filecmp", "fileinput",
    "fnmatch", "formatter", "fractions", "ftplib", "functools", "gc",
    "getopt", "getpass", "gettext", "glob", "grp", "gzip", "hashlib",
    "heapq", "hmac", "html", "http", "idlelib", "imaplib", "imghdr",
    "imp", "importlib", "inspect", "io", "ipaddress", "itertools",
    "json", "keyword", "lib2to3", "linecache", "locale", "logging",
    "lzma", "mailbox", "mailcap", "marshal", "math", "mimetypes",
    "mmap", "modulefinder", "multiprocessing", "netrc", "nis", "nntplib",
    "numbers", "operator", "optparse", "os", "ossaudiodev", "parser",
    "pathlib", "pdb", "pickle", "pickletools", "pipes", "pkgutil",
    "platform", "plistlib", "poplib", "posix", "posixpath", "pprint",
    "profile", "pstats", "pty", "pwd", "py_compile", "pyclbr",
    "pydoc", "queue", "quopri", "random", "re", "readline", "reprlib",
    "resource", "rlcompleter", "runpy", "sched", "secrets", "select",
    "selectors", "shelve", "shlex", "shutil", "signal", "site",
    "smtpd", "smtplib", "sndhdr", "socket", "socketserver", "sqlite3",
    "sre_compile", "sre_constants", "sre_parse", "ssl", "stat",
    "statistics", "string", "stringprep", "struct", "subprocess",
    "sunau", "symtable", "sys", "sysconfig", "syslog", "tabnanny",
    "tarfile", "telnetlib", "tempfile", "termios", "test", "textwrap",
    "threading", "time", "timeit", "tkinter", "token", "tokenize",
    "tomllib", "trace", "traceback", "tracemalloc", "tty", "turtle",
    "turtledemo", "types", "typing", "unicodedata", "unittest", "urllib",
    "uu", "uuid", "venv", "warnings", "wave", "weakref", "webbrowser",
    "winreg", "winsound", "wsgiref", "xdrlib", "xml", "xmlrpc",
    "zipapp", "zipfile", "zipimport", "zlib", "_thread", "__future__",
})


def scan_imports(code: str) -> list[str]:
    """Static-analyse Python code and return third-party modules to install.

    Parses ``import X`` and ``from X import …`` statements, filters out
    stdlib modules, and maps module names to pip package names.
    """
    import_re = re.compile(
        r"^\s*(?:import|from)\s+([\w]+)", re.MULTILINE,
    )
    modules = import_re.findall(code)
    packages: list[str] = []
    seen: set[str] = set()
    for mod in modules:
        top = mod.split(".")[0]
        if top in _STDLIB_MODULES or top.startswith("_"):
            continue
        pip_name = _PIP_NAME_MAP.get(top, top)
        if pip_name not in seen:
            seen.add(pip_name)
            packages.append(pip_name)
    return packages


def check_installed(packages: list[str]) -> list[str]:
    """Return the subset of *packages* that are NOT installed in the sandbox."""
    if not packages:
        return []
    sandbox_py = str(_ensure_sandbox())
    missing: list[str] = []
    for pkg in packages:
        # Use the import name (reverse-map pip→module where possible)
        module_name = pkg
        for mod, pip in _PIP_NAME_MAP.items():
            if pip == pkg:
                module_name = mod
                break
        proc = subprocess.run(
            [sandbox_py, "-c", f"import {module_name}"],
            capture_output=True, text=True, timeout=15,
        )
        if proc.returncode != 0:
            missing.append(pkg)
    return missing


def detect_missing_packages(stderr: str) -> list[str]:
    """Parse stderr and return a list of pip package names to install."""
    modules = _MODULE_ERROR_RE.findall(stderr)
    # Convert module names to pip package names
    packages = []
    seen = set()
    for mod in modules:
        top = mod.split(".")[0]  # e.g. "pandas.core" → "pandas"
        pip_name = _PIP_NAME_MAP.get(top, top)
        if pip_name not in seen:
            seen.add(pip_name)
            packages.append(pip_name)
    return packages


def install_packages(packages: list[str]) -> dict:
    """Install pip packages into the isolated sandbox venv (not the backend)."""
    if not packages:
        return {"error": "No packages specified."}
    try:
        sandbox_py = str(_ensure_sandbox())
        proc = subprocess.run(
            [sandbox_py, "-m", "pip", "install"] + packages,
            capture_output=True,
            text=True,
            timeout=300,  # 5 min for install
        )
        return {
            "exit_code": proc.returncode,
            "stdout": proc.stdout[-4000:] if proc.stdout else "",
            "stderr": proc.stderr[-2000:] if proc.stderr else "",
            "installed": packages if proc.returncode == 0 else [],
        }
    except subprocess.TimeoutExpired:
        return {"error": "Package installation timed out after 5 minutes."}
    except Exception as e:
        return {"error": str(e)}


# ── Registry ──────────────────────────────────────────────────────

_HANDLERS: dict[str, Callable] = {
    "word_count":          _word_count,
    "char_count":          _char_count,
    "heading_extraction":  _heading_extraction,
    "search_document":     _search_document,
    "extract_code_blocks": _extract_code_blocks,
    "extract_todos":       _extract_todos,
    "execute_python":      _execute_python,
    "execute_shell":       _execute_shell,
}

# ── OpenAI tool schema ────────────────────────────────────────────

TOOL_DEFINITIONS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "word_count",
            "description": "Count the number of words in the current document.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "char_count",
            "description": "Count the number of characters in the current document.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "heading_extraction",
            "description": "Extract all Markdown headings (# to ######) from the document.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_document",
            "description": "Search the document for lines containing a query string.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The text to search for.",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "extract_code_blocks",
            "description": "Extract all fenced code blocks from the document with their language, line number, and content.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "extract_todos",
            "description": "Extract all TODO items, checkboxes, FIXME/HACK/XXX markers from the document with progress stats.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]


def dispatch_tool(name: str, arguments: dict, document: str) -> str:
    """Execute a tool by name and return the result as a JSON string."""
    handler = _HANDLERS.get(name)
    if not handler:
        return json.dumps({"error": f"Unknown tool: {name}"})
    return handler(document=document, **arguments)