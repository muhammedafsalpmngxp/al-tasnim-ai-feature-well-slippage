"""
Structured, colored console logging for everything the backend does, not just the SQL
agent pipeline: schema introspection, the delay-analysis answer, database switching, and
the well/investigation queries all print through this too.

Every stage of an operation prints one line: a fixed-width colored stage label, then a
short status message — so watching the terminal shows exactly what's happening as it
happens, instead of either silence or a wall of undifferentiated log text.

This is display only — it never raises, never changes control flow, and falls back to
plain `print` if `rich` isn't installed for any reason, so a missing/broken terminal
dependency can never break the pipeline itself.
"""

try:
    from rich.console import Console
    from rich.text import Text

    # legacy_windows=False: without it, rich auto-detects some Windows terminals (older
    # cmd.exe, and some non-interactive/piped contexts) as needing its legacy Win32
    # console API instead of standard ANSI codes — and that path is fragile: it has been
    # observed to raise OSError("Invalid argument") when stdout isn't a genuine console
    # handle (e.g. piped output), which would crash the SQL pipeline over a cosmetic
    # logging call. Forcing ANSI mode avoids that codepath entirely; every terminal this
    # app actually targets (Windows Terminal, PowerShell 7+, VS Code) supports it.
    _console = Console(legacy_windows=False)
    _RICH_AVAILABLE = True
except ImportError:
    _console = None
    _RICH_AVAILABLE = False


# Widest label in use is "Investigation" (13 chars) — keep this ahead of it so every
# line's message column starts in the same place regardless of which stage logged it.
_LABEL_WIDTH = 13

# Default color per stage when a call doesn't say pass/fail explicitly (e.g. the LLM
# stage, which just reports timing, not a verdict).
_STAGE_COLOR = {
    "LLM": "cyan",
    "SQL Author": "blue",
    "Verifier": "yellow",
    "Validator": "magenta",
    "Write": "white",
    "Schema": "bright_blue",
    "Hints": "bright_magenta",
    "Fingerprint": "bright_cyan",
    "Database": "bright_yellow",
    "Investigation": "blue",
    "Answer": "green",
    "Wells": "bright_blue",
    "Calculation": "bright_cyan",
}


def log_stage(stage, message, ok=None):
    """Print one pipeline log line.

    `stage` — any short label, e.g. "LLM" | "SQL Author" | "Verifier" | "Validator" |
    "Write" | "Schema" | "Hints" | "Fingerprint" | "Database" | "Investigation" |
    "Answer" | "Wells" | "Calculation" — an unlisted stage falls back to plain white.
    `message` — the detail text, already formatted (this function adds no punctuation)
    `ok` — None for a neutral/informational line (uses the stage's default color),
           True to force green (a check passed / a write succeeded),
           False to force red (a check failed / a write was skipped)
    """

    if ok is True:
        color = "green"
    elif ok is False:
        color = "red"
    else:
        color = _STAGE_COLOR.get(stage, "white")

    label = stage.ljust(_LABEL_WIDTH)

    if _RICH_AVAILABLE:
        try:
            # Built with the Text API, not an f-string passed to print(): `message`
            # often contains literal "[...]" (e.g. "[investigation]"), and rich's markup
            # parser would read that as a style tag and silently swallow it. Text.append()
            # never parses its argument as markup, so brackets in the message stay literal.
            line = Text()
            line.append(label, style=color)
            line.append(" " + message)
            _console.print(line)
            return
        except Exception:
            # A display line must never take the pipeline down with it — fall through
            # to the plain fallback below rather than propagate.
            pass

    print(f"{label} {message}")
