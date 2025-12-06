# primus_cli.py
#!/usr/bin/env python3
"""
PRIMUS Command Line Interface
Provides:
 - Chat commands
 - Bootup self-test trigger
 - Simple runtime wrapper passthrough
"""

import argparse
import sys
import traceback
from core.primus_runtime import PrimusRuntime


# -------------------------------------------------------------
# Command Handlers
# -------------------------------------------------------------

def cmd_chat(args):
    runtime = PrimusRuntime()
    try:
        reply = runtime.chat_once(args.message)
        print(reply)
    except Exception as exc:
        print(f"Error: chat_once failed ({exc})")
        traceback.print_exc()


def cmd_bootup_test(_args):
    runtime = PrimusRuntime()
    exit_code = runtime.run_bootup_test()
    sys.exit(exit_code)


# -------------------------------------------------------------
# Argument Parser
# -------------------------------------------------------------

def build_parser():
    parser = argparse.ArgumentParser(
        prog="primus_cli",
        description="PRIMUS OS – Command Line Interface"
    )

    sub = parser.add_subparsers(dest="command")

    # Chat command
    p_chat = sub.add_parser("chat", help="Send a message to PRIMUS")
    p_chat.add_argument("message", type=str, help="Message text for the AI")
    p_chat.set_defaults(func=cmd_chat)

    # Bootup test
    p_test = sub.add_parser("bootup-test", help="Run full system boot self-test")
    p_test.set_defaults(func=cmd_bootup_test)

    return parser


# -------------------------------------------------------------
# Entrypoint
# -------------------------------------------------------------

def main():
    parser = build_parser()
    args = parser.parse_args()

    if not hasattr(args, "func"):
        parser.print_help()
        return

    try:
        args.func(args)
    except Exception as exc:
        print(f"[CLI ERROR] {exc}")
        traceback.print_exc()


if __name__ == "__main__":
    main()