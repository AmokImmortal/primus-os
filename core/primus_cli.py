#!/usr/bin/env python3
import argparse
import logging
import sys
from pathlib import Path

from core.primus_runtime import PrimusRuntime
from core.primus_core import PrimusCore

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


# ---------------------------------------------------------
# command: chat
# ---------------------------------------------------------
def cli_chat(args):
    runtime = PrimusRuntime()
    core = runtime._ensure_core()
    reply = core.chat(message=args.message)
    print(reply)


# ---------------------------------------------------------
# command: cl  (captain's log)
# ---------------------------------------------------------
def cli_captains_log(args):
    runtime = PrimusRuntime()
    core = runtime._ensure_core()
    result = core.captains_log(args.action, args.text)
    print(result)


# ---------------------------------------------------------
# command: rag-index
# ---------------------------------------------------------
def cli_rag_index(args):
    runtime = PrimusRuntime()
    core = runtime._ensure_core()

    path = Path(args.path).resolve()
    core.rag_index(path, recursive=args.recursive)


# ---------------------------------------------------------
# command: rag-search
# ---------------------------------------------------------
def cli_rag_search(args):
    runtime = PrimusRuntime()
    core = runtime._ensure_core()

    index = args.index
    query = args.query
    results = core.rag_retrieve(index, query)

    for score, text in results:
        print(f"[{score:.4f}] {text}")


# ---------------------------------------------------------
# main
# ---------------------------------------------------------
def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    # chat
    p_chat = sub.add_parser("chat")
    p_chat.add_argument("message")
    p_chat.set_defaults(func=cli_chat)

    # captain's log
    p_cl = sub.add_parser("cl")
    p_cl.add_argument("action", choices=["write", "read"])
    p_cl.add_argument("text", nargs="?", default="")
    p_cl.set_defaults(func=cli_captains_log)

    # rag-index
    p_index = sub.add_parser("rag-index")
    p_index.add_argument("path")
    p_index.add_argument("--recursive", action="store_true")
    p_index.set_defaults(func=cli_rag_index)

    # rag-search
    p_search = sub.add_parser("rag-search")
    p_search.add_argument("index")
    p_search.add_argument("query")
    p_search.set_defaults(func=cli_rag_search)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()