#!/usr/bin/env python
"""
primus_cli.py

Top-level command-line interface for the P.R.I.M.U.S OS.

Commands:
    - chat : interactive or one-shot chat with the core model
    - cl   : "Captain's Log" flavored chat (alias of chat with a different mode)
"""

from __future__ import annotations

import argparse
import logging
import sys
from typing import List, Dict, Any

from core.primus_runtime import PrimusRuntime


LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Logging helpers
# ---------------------------------------------------------------------------


def configure_logging(verbose: bool) -> None:
    """Configure root logging for CLI usage."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    LOGGER.debug("Logging initialized (verbose=%s)", verbose)


# ---------------------------------------------------------------------------
# Chat helpers
# ---------------------------------------------------------------------------


def _ensure_core(runtime_mode: str) -> Any:
    """
    Lazily construct PrimusRuntime and return its PrimusCore instance.

    This intentionally goes through PrimusRuntime so that all bootstrapping
    (security, model backend, memory, etc.) stays centralized.
    """
    runtime = PrimusRuntime(mode=runtime_mode)
    LOGGER.info("PrimusRuntime created for CLI (mode=%s).", runtime_mode)

    # _ensure_core() is the same method used by the bootup self-test.
    core = runtime._ensure_core()  # type: ignore[attr-defined]
    LOGGER.info("PrimusCore instance acquired from PrimusRuntime.")
    return core


def _append_user_message(core: Any, session_id: str, text: str) -> None:
    """Append a user message to the session, if SessionManager supports it."""
    sm = getattr(core, "session_manager", None)
    if sm is None:
        LOGGER.warning("SessionManager is not available on PrimusCore; "
                       "skipping user message persistence.")
        return

    append = getattr(sm, "append_message", None)
    if append is None:
        LOGGER.warning(
            "SessionManager.append_message() not found; message persistence disabled."
        )
        return

    append(session_id=session_id, role="user", content=text, metadata={"origin": "cli"})


def _append_assistant_message(core: Any, session_id: str, text: str) -> None:
    """Append an assistant message to the session, if SessionManager supports it."""
    sm = getattr(core, "session_manager", None)
    if sm is None:
        return

    append = getattr(sm, "append_message", None)
    if append is None:
        return

    append(
        session_id=session_id,
        role="assistant",
        content=text,
        metadata={"origin": "cli"},
    )


def _get_history(core: Any, session_id: str) -> List[Dict[str, Any]]:
    """
    Retrieve chat history for a session, if supported.

    Returns a list of message dicts shaped like:
        {"role": "user" | "assistant" | "system", "content": "..."}
    If history is unavailable, returns an empty list.
    """
    sm = getattr(core, "session_manager", None)
    if sm is None:
        LOGGER.debug("SessionManager missing; returning empty history.")
        return []

    get_history = getattr(sm, "get_history", None)
    if get_history is None:
        LOGGER.debug("SessionManager.get_history() missing; returning empty history.")
        return []

    history = get_history(session_id=session_id)
    if not isinstance(history, list):
        LOGGER.debug(
            "SessionManager.get_history() returned non-list (%s); coercing to [].",
            type(history),
        )
        return []

    # We keep it generic here; ModelManager can adapt to this structure.
    return history


def _ensure_session(core: Any, mode: str) -> str:
    """
    Ensure a new session is created for CLI usage and return its session_id.

    This is defensive: if SessionManager is missing, we fabricate a dummy ID
    so that downstream logic can still run.
    """
    sm = getattr(core, "session_manager", None)
    if sm is None:
        LOGGER.warning(
            "SessionManager is not available on PrimusCore; using ephemeral session."
        )
        return "ephemeral-cli-session"

    create_session = getattr(sm, "create_session", None)
    if create_session is None:
        LOGGER.warning(
            "SessionManager.create_session() missing; using ephemeral session."
        )
        return "ephemeral-cli-session"

    session = create_session(
        metadata={
            "origin": "cli",
            "mode": mode,
        }
    )
    # Accept either a plain string or an object with id attribute.
    if isinstance(session, str):
        session_id = session
    else:
        session_id = getattr(session, "id", None) or getattr(
            session, "session_id", "ephemeral-cli-session"
        )

    LOGGER.info("CLI session established (session_id=%s).", session_id)
    return session_id


def _generate_model_reply(core: Any, history: List[Dict[str, Any]]) -> str:
    """
    Generate a reply from the model using ModelManager.

    This assumes ModelManager exposes either:
        - generate_reply(history)
        - chat(history=history)

    It tries both, in that order, to stay compatible with different versions.
    """
    mm = getattr(core, "model_manager", None)
    if mm is None:
        LOGGER.error("ModelManager is not available on PrimusCore.")
        return "[ERROR] Model backend is not available."

    # Try a couple of plausible APIs to maximize compatibility.
    for attr in ("generate_reply", "chat"):
        fn = getattr(mm, attr, None)
        if fn is None:
            continue

        try:
            LOGGER.debug("Invoking ModelManager.%s() for reply.", attr)
            reply = fn(history)  # type: ignore[call-arg]
            if reply is None:
                return "[WARN] Model returned no content."
            if not isinstance(reply, str):
                reply = str(reply)
            return reply
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("Error while calling ModelManager.%s(): %s", attr, exc)
            return "[ERROR] Model backend failed to generate a reply."

    LOGGER.error(
        "ModelManager has neither 'generate_reply' nor 'chat' methods; "
        "cannot perform chat."
    )
    return "[ERROR] Model backend does not expose a chat interface."


def _run_single_turn_chat(core: Any, session_id: str, message: str) -> int:
    """Handle a single-turn chat interaction and exit."""
    _append_user_message(core, session_id, message)
    history = _get_history(core, session_id)
    reply = _generate_model_reply(core, history)
    _append_assistant_message(core, session_id, reply)
    print(reply)
    return 0


def _run_interactive_chat(core: Any, session_id: str) -> int:
    """
    Run an interactive REPL-style chat loop.

    The loop exits on EOF (Ctrl+D / Ctrl+Z) or when the user types 'exit' or 'quit'.
    """
    print("P.R.I.M.U.S interactive chat. Type 'exit' or 'quit' to leave.\n")

    while True:
        try:
            user_input = input("You> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n[CLI] Exiting chat.")
            return 0

        if not user_input:
            continue

        if user_input.lower() in {"exit", "quit"}:
            print("[CLI] Goodbye.")
            return 0

        _append_user_message(core, session_id, user_input)
        history = _get_history(core, session_id)
        reply = _generate_model_reply(core, history)
        _append_assistant_message(core, session_id, reply)
        print(f"PRIMUS> {reply}")


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------


def handle_chat_command(args: argparse.Namespace) -> int:
    """Entry point for the 'chat' subcommand."""
    configure_logging(args.verbose)
    LOGGER.debug("Handling 'chat' command with args: %s", args)

    core = _ensure_core(runtime_mode=args.mode)
    session_id = _ensure_session(core, mode=args.mode)

    if args.message:
        return _run_single_turn_chat(core, session_id, args.message)

    return _run_interactive_chat(core, session_id)


def handle_captains_log_command(args: argparse.Namespace) -> int:
    """
    Entry point for the 'cl' subcommand.

    This is an alias for 'chat' with a Captain's-Log oriented mode.
    """
    # Force mode to a dedicated value so security/logging can treat it specially.
    args.mode = "captains_log"
    return handle_chat_command(args)


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser for primus_cli."""
    parser = argparse.ArgumentParser(
        prog="primus_cli.py",
        description="P.R.I.M.U.S OS command-line interface.",
    )

    subparsers = parser.add_subparsers(
        title="commands",
        dest="command",
        metavar="{chat,cl}",
        help="Available commands",
    )

    # --- chat ---
    chat_parser = subparsers.add_parser(
        "chat",
        help="Chat with the P.R.I.M.U.S core model.",
    )
    chat_parser.add_argument(
        "-m",
        "--message",
        help="Send a single message and print the reply, then exit.",
    )
    chat_parser.add_argument(
        "--mode",
        choices=["normal", "captains_log"],
        default="normal",
        help="Runtime mode to use (default: normal).",
    )
    chat_parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose (DEBUG) logging output.",
    )
    chat_parser.set_defaults(func=handle_chat_command)

    # --- cl (Captain's Log) ---
    cl_parser = subparsers.add_parser(
        "cl",
        help="Captain's Log flavored chat (alias of 'chat').",
    )
    cl_parser.add_argument(
        "-m",
        "--message",
        help="Send a single Captain's-Log style message and exit.",
    )
    cl_parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose (DEBUG) logging output.",
    )
    cl_parser.set_defaults(func=handle_captains_log_command)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Main entry point for primus_cli."""
    if argv is None:
        argv = sys.argv[1:]

    parser = build_arg_parser()
    args = parser.parse_args(argv)

    # If no command provided, show help and exit with error (argparse default
    # behavior is a bit unfriendly here, so we make it explicit).
    if not hasattr(args, "func"):
        parser.print_help()
        return 1

    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())