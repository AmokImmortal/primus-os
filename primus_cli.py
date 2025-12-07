#!/usr/bin/env python3
"""
primus_cli.py

Top-level CLI for PRIMUS OS.

Commands:
  - chat        : single-turn chat (RAG-aware via PrimusRuntime.chat_once)
  - chat-rag    : alias for RAG-aware chat
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
# Command: chat (RAG-aware via PrimusRuntime.chat_once)                       #
# --------------------------------------------------------------------------- #


def cli_chat(args: argparse.Namespace) -> None:
    runtime = PrimusRuntime()
    reply = runtime.chat_once(args.message)
    print(reply)


def cli_chat_rag(args: argparse.Namespace) -> None:
    runtime = PrimusRuntime()
    reply = runtime.chat_once(args.message)
    print(reply)


# --------------------------------------------------------------------------- #
# Command: Captain's Log (if exposed on PrimusCore)                           #
# --------------------------------------------------------------------------- #


def cli_captains_log(args: argparse.Namespace) -> None:
    runtime = PrimusRuntime()
    core = runtime._ensure_core()  # type: ignore[attr-defined]

    handler = getattr(core, "captains_log", None)
    if not callable(handler):
        print("Captain's Log API is not available on PrimusCore.")
        return

    result = handler(args.action, args.text or "")
    print(result)


# --------------------------------------------------------------------------- #
# Command: rag-index                                                          #
# --------------------------------------------------------------------------- #


def cli_rag_index(args: argparse.Namespace) -> None:
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

    # Captain's Log controls
    p_cl = add_command("cl", help="Captain's Log Master Root Mode controls")
    cl_sub = p_cl.add_subparsers(dest="cl_command", required=True)
    cl_enter = cl_sub.add_parser("enter", help="Enter Captain's Log Master Root Mode")
    cl_enter.set_defaults(func=cmd_captains_log)
    cl_exit = cl_sub.add_parser("exit", help="Exit Captain's Log Master Root Mode")
    cl_exit.set_defaults(func=cmd_captains_log)
    cl_status = cl_sub.add_parser("status", help="Show Captain's Log status")
    cl_status.set_defaults(func=cmd_captains_log)

    # Captain's Log controls
    p_cl = add_command("cl", help="Captain's Log Master Root Mode controls")
    cl_sub = p_cl.add_subparsers(dest="cl_command", required=True)
    cl_enter = cl_sub.add_parser("enter", help="Enter Captain's Log Master Root Mode")
    cl_enter.set_defaults(func=cmd_captains_log)
    cl_exit = cl_sub.add_parser("exit", help="Exit Captain's Log Master Root Mode")
    cl_exit.set_defaults(func=cmd_captains_log)
    cl_status = cl_sub.add_parser("status", help="Show Captain's Log status")
    cl_status.set_defaults(func=cmd_captains_log)

    # Captain's Log controls
    p_cl = add_command("cl", help="Captain's Log Master Root Mode controls")
    cl_sub = p_cl.add_subparsers(dest="cl_command", required=True)
    cl_enter = cl_sub.add_parser("enter", help="Enter Captain's Log Master Root Mode")
    cl_enter.set_defaults(func=cmd_captains_log)
    cl_exit = cl_sub.add_parser("exit", help="Exit Captain's Log Master Root Mode")
    cl_exit.set_defaults(func=cmd_captains_log)
    cl_status = cl_sub.add_parser("status", help="Show Captain's Log status")
    cl_status.set_defaults(func=cmd_captains_log)

    # chat
    p_chat = subparsers.add_parser(
        "chat",
        help="Single-turn chat (RAG-aware, via PrimusRuntime.chat_once)",
    )
    p_chat.add_argument("message", help="User message to send to PRIMUS")
    p_chat.set_defaults(func=cli_chat)

    # chat-rag (alias)
    p_chat_rag = subparsers.add_parser(
        "chat-rag",
        help="Alias for RAG-aware chat (reserved for future advanced options)",
    )
    p_chat_rag.add_argument("message", help="User message to send to PRIMUS (RAG-aware)")
    p_chat_rag.set_defaults(func=cli_chat_rag)

    # Captain's Log (simple write/read)
    p_cl = subparsers.add_parser(
        "cl",
        help="Captain's Log controls (if available on PrimusCore)",
    )
    p_cl.add_argument("action", choices=["write", "read"], help="Action to perform")
    p_cl.add_argument(
        "text",
        nargs="?",
        default="",
        help="Text to write (for 'write' action); ignored for 'read'",
    )
    p_cl.set_defaults(func=cli_captains_log)

    # rag-index
    p_index = subparsers.add_parser(
        "rag-index",
        help="Index a path into a named RAG index",
    )
    p_index.add_argument("path", help="File or directory to index")
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
    p_search.add_argument("index", help="Index name (e.g., 'docs')")
    p_search.add_argument("query", help="Search query text")
    p_search.add_argument(
        "--top-k",
        type=int,
        default=3,
        help="Number of top results to return (default: 3)",
    )
    p_search.set_defaults(func=cli_rag_search)

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
