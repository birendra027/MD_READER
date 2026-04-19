"""
chatbot/commands.py
Slash-command parser and registry.

Supported commands:
    /summarise  - Summarise the document
    /overview   - High-level outline
    /keypoints  - Extract key points
    /code       - Analyse code blocks in the document
    /todo       - Extract and list TODO / task items
    /verify     - Verify document content for correctness
    /run        - Execute code blocks from the document
    /clear      - Clear session (handled client-side, acknowledged by server)
    /export     - Return the raw document content
    /help       - Show available commands
"""

from __future__ import annotations
import re
from chatbot.models import ParsedCommand

# Map of slash-command names -> internal names
_REGISTRY: dict[str, str] = {
    "summarise": "summarise",
    "summarize": "summarise",       # US spelling alias
    "summary":   "summarise",
    "overview":  "overview",
    "keypoints": "keypoints",
    "key":       "keypoints",
    "code":      "code",
    "analyse":   "code",            # alias
    "analyze":   "code",            # US spelling alias
    "todo":      "todo",
    "todos":     "todo",
    "tasks":     "todo",
    "verify":    "verify",
    "check":     "verify",
    "run":       "run",
    "exec":      "run",
    "execute":   "run",
    "clear":     "clear",
    "export":    "export",
    "help":      "help",
}

# Commands that skip the LLM entirely
CLIENT_COMMANDS: set[str] = {"clear", "help", "export"}

_CMD_RE = re.compile(r"^/(\w+)\s*(.*)", re.DOTALL)

HELP_TEXT = """\
**Available commands:**

| Command | Description |
|---------|-------------|
| `/summarise` | Summarise the document |
| `/overview` | High-level outline of the document |
| `/keypoints` | Extract key points |
| `/code` | Analyse code blocks in the document |
| `/todo` | Extract and list TODO / task items |
| `/verify` | Verify document content for correctness |
| `/run` | Execute code blocks from the document |
| `/clear` | Clear the conversation |
| `/export` | Return the raw document text |
| `/help` | Show this help message |

You can also type any free-form question about your document.
"""


def parse(user_message: str) -> ParsedCommand:
    """Parse a user message into a ParsedCommand."""
    m = _CMD_RE.match(user_message.strip())
    if not m:
        return ParsedCommand(name=None, args="", original_text=user_message)

    raw_cmd = m.group(1).lower()
    args = m.group(2).strip()
    name = _REGISTRY.get(raw_cmd)

    if name is None:
        # Unknown command - treat as plain text
        return ParsedCommand(name=None, args="", original_text=user_message)

    return ParsedCommand(name=name, args=args, original_text=user_message)