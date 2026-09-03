"""
Shared terminal output helpers.
Consistent styling across all CLI entry points.
"""

import io
import sys

# Force UTF-8 on Windows
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

W = 72  # line width

SEVERITY_COLOR = {
    "CRITICAL": "\033[91m",  # bright red
    "HIGH": "\033[33m",  # yellow
    "MEDIUM": "\033[93m",  # bright yellow
    "LOW": "\033[96m",  # cyan
    "INFO": "\033[37m",  # light grey
}
STATUS_COLOR = {
    "OPEN": "\033[91m",  # red
    "IN_PROGRESS": "\033[93m",  # yellow
    "RESOLVED": "\033[92m",  # green
}
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[92m"
RED = "\033[91m"
CYAN = "\033[96m"
YELLOW = "\033[93m"
GREY = "\033[37m"


def _no_color() -> bool:
    import os

    return os.environ.get("NO_COLOR", "") != "" or not sys.stdout.isatty()


def c(text: str, code: str) -> str:
    if _no_color():
        return text
    return f"{code}{text}{RESET}"


def banner(title: str, subtitle: str = "") -> None:
    print()
    print(c("=" * W, DIM))
    print(f"  {c(title, BOLD)}")
    if subtitle:
        print(f"  {c(subtitle, DIM)}")
    print(c("=" * W, DIM))


def section(title: str) -> None:
    print()
    print(c(f"  {title}", BOLD))
    print(c("  " + "-" * (W - 2), DIM))


def step(n: int, label: str, actor: str = "") -> None:
    actor_str = f"  {c(actor, DIM)}" if actor else ""
    num = c(f"[{n:02d}]", CYAN)
    print(f"\n{num} {c(label, BOLD)}{actor_str}")


def ok(msg: str) -> None:
    print(f"      {c('OK', GREEN)}  {msg}")


def fail(msg: str) -> None:
    print(f"      {c('FAIL', RED)}  {msg}")


def info(key: str, value: str, indent: int = 6) -> None:
    pad = " " * indent
    print(f"{pad}{c(key + ':', DIM)}  {value}")


def row(label: str, value: str, width: int = 16, indent: int = 6) -> None:
    pad = " " * indent
    print(f"{pad}{c(label.ljust(width), DIM)}  {value}")


def finding_row(f: dict) -> None:
    sev = f.get("severity", "")
    sta = f.get("status", "")
    sev_str = c(f"[{sev:<8}]", SEVERITY_COLOR.get(sev, RESET))
    sta_str = c(f"{sta:<11}", STATUS_COLOR.get(sta, RESET))
    title = f.get("title", "")[:52]
    print(f"      {sev_str}  {sta_str}  {title}")


def http_result(method: str, path: str, status: int, note: str = "") -> None:
    color = GREEN if 200 <= status < 300 else (YELLOW if status < 500 else RED)
    code = c(str(status), color)
    meth = c(f"{method:<6}", DIM)
    note_str = f"  {c(note, DIM)}" if note else ""
    print(f"      {meth}  {path}  ->  {code}{note_str}")


def audit_row(log: dict) -> None:
    user = c(log.get("username", "?"), CYAN)
    old = c(log.get("old_value", "-"), YELLOW)
    new = c(log.get("new_value", "-"), GREEN)
    ts = c(log.get("timestamp", "")[:19].replace("T", " "), DIM)
    print(f"      {user}  {old} -> {new}  {ts}")


def divider() -> None:
    print(c("  " + "-" * (W - 2), DIM))


def blank() -> None:
    print()


def success(msg: str) -> None:
    print(f"\n  {c('', GREEN)}{c(msg, BOLD)}")


def error(msg: str) -> None:
    print(f"\n  {c('ERROR', RED)}  {msg}")


def warn(msg: str) -> None:
    print(f"\n  {c('WARN', YELLOW)}  {msg}")
