#!/usr/bin/env python3
"""
primus_cli.py

Command-line interface for PRIMUS OS (Core developer/admin CLI).
- One-file entrypoint to inspect, control, and interact with the system.
- Designed to be defensive: if a core component/class/method is missing
  the CLI still runs and provides clear guidance.

Place this file at:
"C:\\P.R.I.M.U.S OS\\System\\primus_cli.py"

Usage examples:
    python primus_cli.py status
    python primus_cli.py self-test
    python primus_cli.py start
    python primus_cli.py agent list
    python primus_cli.py agent call FileAgent '{"action":"ping"}'
    python primus_cli.py rag ingest --path test_docs
    python primus_cli.py rag search --query "what is inside test1?"
    python primus_cli.py chat
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from typing import Optional, Any, Dict

# ---------------------------------------------------------------------
# Path setup so imports work when running from the System directory
# ---------------------------------------------------------------------

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = THIS_DIR
CORE_DIR = os.path.join(PROJECT_ROOT, "core")
CAPTAINS_LOG_DIR = os.path.join(PROJECT_ROOT, "captains_log")

for p in (PROJECT_ROOT, CORE_DIR, CAPTAINS_LOG_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

# ---------------------------------------------------------------------
# Imports with fallbacks
# ---------------------------------------------------------------------

try:
    from core.primus_runtime import PrimusRuntime  # type: ignore
except ImportError:
    from primus_runtime import PrimusRuntime  # type: ignore

try:
    from captains_log.cl_manager import get_manager as get_cl_manager  # type: ignore
except ImportError:  # defensive; CLI still works for non-CL commands
    def get_cl_manager() -> Any:  # type: ignore
        raise RuntimeError("Captain's Log manager is not available")


logger = logging.getLogger("primus_cli")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------


def _make_runtime(mode: str = "normal") -> PrimusRuntime:
    """
    Construct a PrimusRuntime suitable for CLI use.
    We prefer non_interactive=True so it does not try to open UI loops.
    """
    try:
        rt = PrimusRuntime(mode=mode, non_interactive=True)
    except TypeError:
        # Fallback if constructor signature is different
        rt = PrimusRuntime()  # type: ignore
    return rt


# ---------------------------------------------------------------------
# Chat command
# ---------------------------------------------------------------------


def cmd_chat(args: argparse.Namespace) -> int:
    runtime = _make_runtime()
    if not hasattr(runtime, "chat_once"):
        print("Runtime does not expose chat_once(); no response available.")
        return 1

    user_message: str = args.message
    try:
        reply = runtime.chat_once(user_message)  # type: ignore[attr-defined]
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("chat_once failed: %s", exc)
        print("Error: chat_once failed; see logs for details.")
        return 1

    if reply is not None:
        print(reply)
    else:
        print("No reply from PRIMUS (None returned).")
    return 0


# ---------------------------------------------------------------------
# Captain's Log commands
# ---------------------------------------------------------------------


def _runtime_cl_status(runtime: PrimusRuntime) -> Optional[Dict[str, Any]]:
    """
    Try to get Captain's Log status via PrimusRuntime, with fallbacks.
    """
    # Preferred: dedicated runtime method if present
    if hasattr(runtime, "get_captains_log_status"):
        try:
            return runtime.get_captains_log_status()  # type: ignore[attr-defined]
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("get_captains_log_status() failed: %s", exc)

    # Fallback: use the Captain's Log manager directly
    try:
        mgr = get_cl_manager()
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Captain's Log manager not available: %s", exc)
        return None

    # Try several possible manager APIs
    for attr in ("get_status", "get_state", "status"):
        if hasattr(mgr, attr):
            try:
                status = getattr(mgr, attr)()
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("Captain's Log manager.%s() failed: %s", attr, exc)
                return None

            # Normalize to dict if needed
            if isinstance(status, dict):
                return status
            # Maybe it's a dataclass-like object with attributes
            active = getattr(status, "active", None)
            if active is None:
                active = getattr(status, "is_active", None)
            mode = getattr(status, "mode", None)
            return {"active": active, "mode": mode}

    return None


def cmd_cl_status(args: argparse.Namespace) -> int:
    runtime = _make_runtime()
    status = _runtime_cl_status(runtime)

    if not status:
        print("Captain's Log system : UNKNOWN (status unavailable)")
        return 1

    active = status.get("active") or status.get("is_active")
    mode = status.get("mode", "unknown")
    print(f"Captain's Log system : OK (mode={mode})")
    return 0


def cmd_cl_enter(args: argparse.Namespace) -> int:
    runtime = _make_runtime()
    logger.info("PrimusRuntime: enter Captain's Log requested.")

    # Preferred: runtime method
    if hasattr(runtime, "enter_captains_log"):
        try:
            runtime.enter_captains_log()  # type: ignore[attr-defined]
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("enter_captains_log() failed: %s", exc)
            print("Error: failed to enter Captain's Log; see logs for details.")
            return 1
    else:
        # Fallback: direct manager call
        try:
            mgr = get_cl_manager()
            if hasattr(mgr, "enter"):
                mgr.enter()
            elif hasattr(mgr, "activate"):
                mgr.activate()
            else:
                print("Captain's Log manager does not support enter/activate.")
                return 1
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Captain's Log manager enter failed: %s", exc)
            print("Error: failed to enter Captain's Log; see logs for details.")
            return 1

    print("Captain's Log Master Root Mode: ACTIVE")
    return 0


def cmd_cl_exit(args: argparse.Namespace) -> int:
    runtime = _make_runtime()
    logger.info("PrimusRuntime: exit Captain's Log requested.")

    # Preferred: runtime method
    if hasattr(runtime, "exit_captains_log"):
        try:
            runtime.exit_captains_log()  # type: ignore[attr-defined]
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("exit_captains_log() failed: %s", exc)
            print("Error: failed to exit Captain's Log; see logs for details.")
            return 1
    else:
        # Fallback: direct manager call
        try:
            mgr = get_cl_manager()
            if hasattr(mgr, "exit"):
                mgr.exit()
            elif hasattr(mgr, "deactivate"):
                mgr.deactivate()
            else:
                print("Captain's Log manager does not support exit/deactivate.")
                return 1
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Captain's Log manager exit failed: %s", exc)
            print("Error: failed to exit Captain's Log; see logs for details.")
            return 1

    print("Captain's Log Master Root Mode: INACTIVE")
    return 0


# ---------------------------------------------------------------------
# Bootstrap / argument parsing
# ---------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="PRIMUS OS command-line interface",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Captain's Log controls
    p_cl = sub.add_parser("cl", help="Captain's Log Master Root Mode controls")
    cl_sub = p_cl.add_subparsers(dest="cl_command", required=True)
    cl_enter = cl_sub.add_parser("enter", help="Enter Captain's Log Master Root Mode")
    cl_enter.set_defaults(func=cmd_captains_log)
    cl_exit = cl_sub.add_parser("exit", help="Exit Captain's Log Master Root Mode")
    cl_exit.set_defaults(func=cmd_captains_log)
    cl_status = cl_sub.add_parser("status", help="Show Captain's Log status")
    cl_status.set_defaults(func=cmd_captains_log)

    # chat
    chat_p = subparsers.add_parser(
        "chat",
        help="Send a single message to PRIMUS and print the reply.",
    )
    chat_p.add_argument("message", help="User message to send to PRIMUS.")
    chat_p.set_defaults(func=cmd_chat)

    # captain's log group
    cl_p = subparsers.add_parser(
        "cl",
        help="Captain's Log commands (status/enter/exit).",
    )
    cl_sub = cl_p.add_subparsers(dest="cl_command", required=True)

    cl_status_p = cl_sub.add_parser("status", help="Show Captain's Log status.")
    cl_status_p.set_defaults(func=cmd_cl_status)

    cl_enter_p = cl_sub.add_parser("enter", help="Enter Master Root Captain's Log mode.")
    cl_enter_p.set_defaults(func=cmd_cl_enter)

    cl_exit_p = cl_sub.add_parser("exit", help="Exit Master Root Captain's Log mode.")
    cl_exit_p.set_defaults(func=cmd_cl_exit)

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    func = getattr(args, "func", None)
    if func is None:
        parser.print_help()
        return 1

    return int(func(args))


if __name__ == "__main__":
    raise SystemExit(main())






