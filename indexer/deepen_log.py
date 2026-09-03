#!/usr/bin/env python3
"""
Shared logging helper for deepen scripts.

Every deepen_* script (deepen_loop.py, deepen_batch1.py, deepen_aws_v2.py,
deepen_batch.py, and any future child) writes its output to stdout AND
appends to data/logs/deepen.log, so one file holds the full history of all
deepening runs.

Usage — at the top of a deepen script, BEFORE other imports/print calls:

    from deepen_log import install
    install(__file__)

That's it. install() returns nothing; from then on every print() and any
uncaught exception traceback is mirrored to deepen.log automatically.

Log rotation: keeps ~5 MB (rotates deepen.log -> deepen.log.1).
"""
from __future__ import annotations

import builtins
import sys
import threading
import traceback
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
LOG_DIR = BASE / "data" / "logs"
LOG_FILE = LOG_DIR / "deepen.log"
MAX_BYTES = 5 * 1024 * 1024  # rotate at 5 MB

_LOG_LOCK = threading.Lock()  # parallel crawlers log from many threads


def _rotate_if_needed():
    try:
        if LOG_FILE.exists() and LOG_FILE.stat().st_size > MAX_BYTES:
            LOG_FILE.replace(LOG_FILE.with_suffix(".log.1"))
    except OSError:
        pass  # rotation is best-effort


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log_write(line: str):
    """Append one already-formatted line to deepen.log (thread-safe, best-effort)."""
    if not line:
        return
    try:
        with _LOG_LOCK:
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            _rotate_if_needed()
            with LOG_FILE.open("a", encoding="utf-8") as f:
                f.write(line)
    except OSError:
        pass  # never let logging break the crawl


def install(script_path) -> None:
    """
    Mirror stdout prints + crash tracebacks into deepen.log.
    Call once at module import time from any deepen_* script.
    """
    name = Path(script_path).name
    log_write(f"\n{'=' * 70}\n[{_stamp()}] === {name} started (pid {__import__('os').getpid()}) ===\n")

    original_print = builtins.print
    _print_lock = threading.Lock()

    def print_tee(*args, **kwargs):
        # render exactly like print() would
        sep = kwargs.get("sep", " ")
        end = kwargs.get("end", "\n")
        text = sep.join(str(a) for a in args) + end
        with _print_lock:  # keep console + log lines whole under threads
            original_print(*args, **kwargs)
            log_write(text)

    builtins.print = print_tee

    def _excepthook(tp, val, tb):
        import io
        buf = io.StringIO()
        traceback.print_exception(tp, val, tb, file=buf)
        original_print(buf.getvalue())
        log_write(f"[{_stamp()}] CRASH in {name}:\n{buf.getvalue()}\n")
        sys.__excepthook__(tp, val, tb)

    sys.excepthook = _excepthook
