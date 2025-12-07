import argparse
import sys
from typing import Any, Dict, List

from .cl_manager import get_manager


def cmd_status() -> int:
    mgr = get_manager()
    status = mgr.get_status()
    mode = status.get("mode", "unknown")
    active = status.get("active", False)
    print(f"Captain's Log system : OK (mode={mode}, active={active})")
    return 0


def cmd_enter() -> int:
    mgr = get_manager()
    mgr.enter()
    print("Captain's Log Master Root Mode: ACTIVE")
    return 0


def cmd_exit() -> int:
    mgr = get_manager()
    mgr.exit()
    print("Captain's Log Master Root Mode: INACTIVE")
    return 0


def cmd_write(text: str) -> int:
    mgr = get_manager()
    try:
        entry = mgr.add_journal_entry(text)
    except PermissionError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    eid = entry.get("id", "<unknown>")
    print(f"Captain's Log entry created with id={eid}")
    return 0


def _format_entry(entry: Dict[str, Any]) -> str:
    eid = entry.get("id", "")
    ts = entry.get("timestamp", "")
    mode = entry.get("mode", "")
    text = entry.get("text", "")
    return f"[id={eid}] [ts={ts}] [mode={mode}]\n{text}\n"


def cmd_list(limit: int | None) -> int:
    mgr = get_manager()
    try:
        entries: List[Dict[str, Any]] = mgr.list_journal_entries()
    except PermissionError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    if limit is not None:
        entries = entries[-limit:]

    if not entries:
        print("No Captain's Log entries found.")
        return 0

    print(f"Captain's Log entries (showing {len(entries)}):")
    print("-" * 40)
    for e in entries:
        print(_format_entry(e))
        print("-" * 40)
    return 0


def cmd_search(query: str, limit: int) -> int:
    mgr = get_manager()
    try:
        results = mgr.search_rag(query, limit=limit)
    except PermissionError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    if not results:
        print(f"No Captain's Log entries matched query: {query!r}")
        return 0

    print(f"Search results for {query!r} (showing {len(results)}):")
    print("-" * 40)
    for e in results:
        print(_format_entry(e))
        print("-" * 40)
    return 0


def cmd_clear() -> int:
    mgr = get_manager()
    try:
        mgr.clear_journal()
    except PermissionError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    print("Captain's Log journal and RAG memory cleared.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Captain's Log CLI (private Master Root journal and RAG)."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # status
    sub_status = sub.add_parser("status", help="Show Captain's Log mode/status.")
    sub_status.set_defaults(func=lambda args: cmd_status())

    # enter
    sub_enter = sub.add_parser("enter", help="Enter Captain's Log Master Root Mode.")
    sub_enter.set_defaults(func=lambda args: cmd_enter())

    # exit
    sub_exit = sub.add_parser("exit", help="Exit Captain's Log Master Root Mode.")
    sub_exit.set_defaults(func=lambda args: cmd_exit())

    # write
    sub_write = sub.add_parser("write", help="Add a new Captain's Log journal entry.")
    sub_write.add_argument("text", help="Journal text to store.")
    sub_write.set_defaults(func=lambda args: cmd_write(args.text))

    # list
    sub_list = sub.add_parser("list", help="List recent Captain's Log entries.")
    sub_list.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of entries to show (default: all).",
    )
    sub_list.set_defaults(func=lambda args: cmd_list(args.limit))

    # search
    sub_search = sub.add_parser(
        "search", help="Search Captain's Log entries (private RAG)."
    )
    sub_search.add_argument("query", help="Search query string.")
    sub_search.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Maximum number of results to show (default: 5).",
    )
    sub_search.set_defaults(func=lambda args: cmd_search(args.query, args.limit))

    # clear
    sub_clear = sub.add_parser(
        "clear", help="Clear ALL Captain's Log journal + RAG memory."
    )
    sub_clear.set_defaults(func=lambda args: cmd_clear())

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    func = getattr(args, "func", None)
    if func is None:
        parser.print_help()
        return 1
    return int(func(args))


if __name__ == "__main__":
    raise SystemExit(main())






