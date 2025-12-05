# System/primus_cli.py
import argparse
import logging
import os
import sys

# Ensure the System root is on sys.path so "core" can be imported when running from C:\P.R.I.M.U.S OS\System
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

try:
    from core.primus_runtime import PrimusRuntime
except ImportError as e:
    print(f"[FATAL] Failed to import PrimusRuntime from core.primus_runtime: {e}")
    sys.exit(1)


def configure_logging() -> None:
    """
    Configure a simple log file for the CLI, plus stdout logging.
    """
    logs_dir = os.path.join(CURRENT_DIR, "core", "system_logs")
    os.makedirs(logs_dir, exist_ok=True)
    log_path = os.path.join(logs_dir, "primus_cli.log")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="PRIMUS OS Command Line Interface"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Single-turn chat command
    chat_parser = subparsers.add_parser(
        "chat", help="Send a single-turn message to PRIMUS and print the reply."
    )
    chat_parser.add_argument(
        "message",
        type=str,
        help="User message to send to PRIMUS.",
    )

    # Bootup self-test (delegates to PrimusRuntime.run_bootup_test)
    selftest_parser = subparsers.add_parser(
        "bootup-test",
        help="Run the PRIMUS bootup self-test (security, subchats, model backend).",
    )
    # No extra args for now; uses defaults inside PrimusRuntime

    return parser


def cmd_chat(args: argparse.Namespace) -> int:
    """
    Handle: primus_cli.py chat "Hello PRIMUS"
    """
    runtime = PrimusRuntime()
    try:
        if not hasattr(runtime, "chat_once"):
            raise AttributeError(
                "PrimusRuntime.chat_once() is not implemented. "
                "Please ensure core/primus_runtime.py defines chat_once(self, user_message: str) -> str."
            )
        response = runtime.chat_once(args.message)
        print(f"User: {args.message}")
        print(f"PRIMUS: {response}")
        return 0
    except Exception as e:  # noqa: BLE001
        logging.exception("Chat command failed.")
        print(f"Chat error: {e}")
        return 1


def cmd_bootup_test(args: argparse.Namespace) -> int:
    """
    Handle: primus_cli.py bootup-test
    """
    runtime = PrimusRuntime()
    try:
        if not hasattr(runtime, "run_bootup_test"):
            raise AttributeError(
                "PrimusRuntime.run_bootup_test() is not implemented. "
                "Please ensure core/primus_runtime.py defines run_bootup_test(self) -> int."
            )
        rc = runtime.run_bootup_test()
        print(f"Bootup self-test completed with exit code: {rc}")
        return rc
    except Exception as e:  # noqa: BLE001
        logging.exception("Bootup-test command failed.")
        print(f"Bootup-test error: {e}")
        return 1


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "chat":
        return cmd_chat(args)
    if args.command == "bootup-test":
        return cmd_bootup_test(args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())






