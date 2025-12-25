#!/usr/bin/env python3
"""
primus_cli.py

Top-level CLI for PRIMUS OS.

Commands:
  - chat        : session-aware, optional RAG-aware chat via PrimusCore.chat()
  - cl          : Captain's Log controls (if available on core)
  - rag-index   : index a folder of documents into a named RAG index
  - rag-search  : search a named RAG index with a query
"""

import argparse
import logging
from pathlib import Path

from core.primus_runtime import PrimusRuntime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

logger = logging.getLogger("primus_cli")


# --------------------------------------------------------------------------- #
# Command: chat (session-aware, optional RAG)                                 #
# --------------------------------------------------------------------------- #

def cli_session_history(args: argparse.Namespace) -> None:
    """Show recent messages for a given session."""
    runtime = PrimusRuntime()
    core = runtime._ensure_core()  # type: ignore[attr-defined]

    history = getattr(core, "get_session_history", None)
    if not callable(history):
        print("Session history API is not available on PrimusCore.")
        return

    messages = history(args.session, limit=args.limit)
    if not messages:
        print(f"No history found for session {args.session!r}.")
        return

    print(f"Session: {args.session} (showing up to {len(messages)} messages)")
    for idx, msg in enumerate(messages, start=1):
        role = msg.get("role", "user")
        content = msg.get("content", "").strip()
        if not content:
            continue
        print(f"{idx:02d}) {role:9}: {content}")


def cli_session_clear(args: argparse.Namespace) -> None:
    """Clear all messages for a given session."""
    runtime = PrimusRuntime()
    core = runtime._ensure_core()  # type: ignore[attr-defined]

    clearer = getattr(core, "clear_session", None)
    if not callable(clearer):
        print("Session clear API is not available on PrimusCore.")
        return

    clearer(args.session)
    print(f"Cleared session {args.session!r}.")

def cli_chat(args: argparse.Namespace) -> None:
    """
    Chat entrypoint.

    - Uses PrimusRuntime + PrimusCore.chat(...)
    - Supports:
        --session  : conversation ID
        --rag      : enable RAG retrieval
        --index    : RAG index name (when --rag is set)
    """
    runtime = PrimusRuntime()
    core = runtime._ensure_core()  # type: ignore[attr-defined]

    reply = core.chat(
        user_message=args.message,
        session_id=args.session,
        use_rag=args.rag,
        rag_index=args.index,
    )
    print(reply)


# --------------------------------------------------------------------------- #
# Command: Captain's Log (simple write/read)                                  #
# --------------------------------------------------------------------------- #


def cli_captains_log(args: argparse.Namespace) -> None:
    """
    Simple Captain's Log wrapper, if exposed on PrimusCore.

    Actions:
      - write <text>
      - read
      - clear
    """
    runtime = PrimusRuntime()
    core = runtime._ensure_core()  # type: ignore[attr-defined]
    manager = getattr(runtime, "captains_log_manager", None)
    manager_active = False
    if manager and hasattr(manager, "is_active"):
        try:
            manager_active = bool(manager.is_active())
        except Exception:  # noqa: BLE001
            manager_active = False

    has_api = all(
        hasattr(core, attr) for attr in ("captains_log_write", "captains_log_read", "captains_log_clear")
    )
    if not has_api:
        print("Captain's Log is not available in this mode.")
        return

    if not manager:
        print("Captain's Log is disabled. Enable it in your security/captains_log settings or via PRIMUS_CAPTAINS_LOG_DEV=1.")
        return

    try:
        if args.action == "write":
            if not args.text:
                print("No text provided for write action.")
                return
            entry = core.captains_log_write(args.text)
            if entry:
                entry_id = entry.get("id", "<unknown>")
                ts = entry.get("ts") or entry.get("timestamp", "")
                print(f"[OK] Captain's Log entry recorded (id={entry_id}, ts={ts})")
            else:
                print("Captain's Log is disabled. Enable it in your security/captains_log settings or via PRIMUS_CAPTAINS_LOG_DEV=1.")
        elif args.action == "read":
            entries = core.captains_log_read(limit=args.limit)
            if not entries:
                if not manager_active:
                    print("Captain's Log is disabled. Enable it in your security/captains_log settings or via PRIMUS_CAPTAINS_LOG_DEV=1.")
                else:
                    print("No Captain's Log entries found.")
                return
            print(f"Captain's Log entries (showing up to {len(entries)}):")
            for idx, entry in enumerate(entries, 1):
                ts = entry.get("ts") or entry.get("timestamp", "")
                text = (entry.get("text") or "").strip()
                if len(text) > 200:
                    text = text[:200] + "...[truncated]"
                print(f"{idx:02d}) {ts} {text}")
        elif args.action == "clear":
            core.captains_log_clear()
            print("Captain's Log cleared.")
    except PermissionError:
        print("Captain's Log is disabled. Enable it in your security/captains_log settings or dev override.")
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] Captain's Log operation failed: {exc}")


# --------------------------------------------------------------------------- #
# Command: rag-index                                                          #
# --------------------------------------------------------------------------- #


def cli_rag_index(args: argparse.Namespace) -> None:
    """
    Index a path into a named RAG index.
    """
    runtime = PrimusRuntime()
    core = runtime._ensure_core()  # type: ignore[attr-defined]

    path = Path(args.path).resolve()
    index_name = args.name or path.name

    core.rag_index_path(name=index_name, path=str(path), recursive=args.recursive)
    print(f"[OK] Indexed '{path}' as index '{index_name}'")


# --------------------------------------------------------------------------- #
# Command: rag-search                                                         #
# --------------------------------------------------------------------------- #


def cli_rag_search(args: argparse.Namespace) -> None:
    """
    Search a named RAG index with a query.
    """
    runtime = PrimusRuntime()
    core = runtime._ensure_core()  # type: ignore[attr-defined]

    index_name = args.index
    query = args.query
    top_k = args.top_k

    results = core.rag_retrieve(index_name, query, top_k=top_k)

    if not results:
        print(f"[WARN] No results found in index '{index_name}' for query: {query!r}")
        return

    for score, doc in results:
        path = doc.get("path", "<unknown>")
        print(f"[{score:.4f}] {path}")


# --------------------------------------------------------------------------- #
# Parser builder                                                              #
# --------------------------------------------------------------------------- #


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="primus_cli.py",
        description="PRIMUS OS command-line interface",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # chat (session-aware, optional RAG)
    p_chat = subparsers.add_parser(
        "chat",
        help="Chat with optional session and RAG (via PrimusCore.chat)",
    )
    p_chat.add_argument(
        "message",
        help="User message to send to PRIMUS",
    )
    p_chat.add_argument(
        "--session",
        default="cli",
        help="Session ID for conversation history (default: cli)",
    )
    p_chat.add_argument(
        "--rag",
        action="store_true",
        help="Enable RAG retrieval for this turn",
    )
    p_chat.add_argument(
        "--index",
        default="docs",
        help="RAG index name to use when --rag is set (default: docs)",
    )
    p_chat.set_defaults(func=cli_chat)

    # Captain's Log (simple write/read)
    p_cl = subparsers.add_parser(
        "cl",
        help="Captain's Log controls (if available on PrimusCore)",
    )
    p_cl.add_argument(
        "action",
        choices=["write", "read", "clear"],
        help="Action to perform on Captain's Log",
    )
    p_cl.add_argument(
        "text",
        nargs="?",
        default="",
        help="Text to write (for 'write' action); ignored for 'read'",
    )
    p_cl.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Maximum entries to show for 'read' (default: 50)",
    )
    p_cl.set_defaults(func=cli_captains_log)

    # rag-index
    p_index = subparsers.add_parser(
        "rag-index",
        help="Index a path into a named RAG index",
    )
    p_index.add_argument(
        "path",
        help="File or directory to index",
    )
    p_index.add_argument(
        "--name",
        help="Name of the index (defaults to the folder/file name)",
    )
    p_index.add_argument(
        "--recursive",
        action="store_true",
        help="Recursively walk subdirectories when indexing a folder",
    )
    p_index.set_defaults(func=cli_rag_index)

    # rag-search
    p_search = subparsers.add_parser(
        "rag-search",
        help="Search a named RAG index with a query",
    )
    p_search.add_argument(
        "index",
        help="Index name (e.g., 'docs')",
    )
    p_search.add_argument(
        "query",
        help="Search query text",
    )
    p_search.add_argument(
        "--top-k",
        type=int,
        default=3,
        help="Number of top results to return (default: 3)",
    )
    p_search.set_defaults(func=cli_rag_search)

    # session-history
    p_hist = subparsers.add_parser(
        "session-history",
        help="Show recent messages for a given session",
    )
    p_hist.add_argument(
        "--session",
        required=True,
        help="Session ID to inspect",
    )
    p_hist.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum number of messages to show (default: 20)",
    )
    p_hist.set_defaults(func=cli_session_history)

    # session-clear
    p_clear = subparsers.add_parser(
        "session-clear",
        help="Clear all messages for a given session",
    )
    p_clear.add_argument(
        "--session",
        required=True,
        help="Session ID to clear",
    )
    p_clear.set_defaults(func=cli_session_clear)
  
    return parser


# --------------------------------------------------------------------------- #
# Main entrypoint                                                             #
# --------------------------------------------------------------------------- #


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help()
        return
    args.func(args)


if __name__ == "__main__":
    main()
