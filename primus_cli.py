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
import json
import logging
import os
import sys
import traceback
from pathlib import Path
from typing import Any, Dict, Optional
import uuid

# -----------------------
# Basic environment setup
# -----------------------
# Guess system root (assume this file lives in the System root)
SYSTEM_ROOT = Path(__file__).resolve().parent

# Ensure the System root and its parent are importable so core modules load
for _path in (SYSTEM_ROOT, SYSTEM_ROOT.parent):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))
LOG_DIR = SYSTEM_ROOT / "core" / "system_logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "primus_cli.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("primus_cli")


# -----------------------
# Utilities
# -----------------------
def set_log_level(level_name: str) -> None:
    """Update logging verbosity for the CLI session."""

    level = getattr(logging, level_name.upper(), logging.INFO)
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    logger.setLevel(level)

    for handler in root_logger.handlers:
        handler.setLevel(level)
    for handler in logger.handlers:
        handler.setLevel(level)

    logger.debug("Log level set to %s", level_name)


def safe_import(module: str, attr: Optional[str] = None):
    """
    Attempt to import a module or a module.attr. Return the imported object or None.
    """
    try:
        if attr:
            mod = __import__(module, fromlist=[attr])
            return getattr(mod, attr)
        else:
            return __import__(module)
    except Exception as e:
        logger.debug(f"safe_import failed for {module}.{attr or ''}: {e}")
        return None


def pretty_print_object(obj: Any):
    try:
        print(json.dumps(obj, indent=2, default=str, ensure_ascii=False))
    except Exception:
        print(repr(obj))


def show_trace():
    traceback.print_exc()


# -----------------------
# Component helpers
# -----------------------
def get_runtime():
    """
    Try to import a Primus runtime object from a few likely locations.
    Returns (instance, note) where instance may be None.
    """
    # Candidate class paths (based on our project structure variations)
    candidates = [
        ("core.primus_runtime", "PrimusRuntime"),
        ("primus_runtime", "PrimusRuntime"),
        ("core.engine", "PrimusRuntime"),
    ]
    for module, cls in candidates:
        cls_obj = safe_import(module, cls)
        if cls_obj:
            try:
                inst = cls_obj()
                logger.debug(f"Instantiated runtime from {module}.{cls}")
                return inst, f"{module}.{cls}"
            except Exception as e:
                logger.debug(f"Found class {module}.{cls} but failed to instantiate: {e}")
                try:
                    # maybe it's a module-level singleton factory
                    module_obj = safe_import(module)
                    if hasattr(module_obj, "get_runtime"):
                        inst = module_obj.get_runtime()
                        return inst, f"{module}.get_runtime()"
                except Exception:
                    pass
    return None, None


def get_agent_manager():
    # core.agent_manager.AgentManager or core.agent_manager.AgentManagerService
    candidates = [
        ("core.agent_manager", "AgentManager"),
        ("core.agent_manager", "AgentManagerService"),
        ("core.agent_manager", None),
    ]
    for module, cls in candidates:
        if cls:
            cls_obj = safe_import(module, cls)
            if cls_obj:
                try:
                    return cls_obj()
                except Exception:
                    return cls_obj  # maybe class, return class reference
        else:
            mod = safe_import(module)
            if mod:
                # try common factory names
                if hasattr(mod, "AgentManager"):
                    try:
                        return getattr(mod, "AgentManager")()
                    except Exception:
                        return getattr(mod, "AgentManager")
                return mod
    return None


def get_rag_manager():
    # rag_manager may live in core or rag package
    candidates = [
        ("core.rag_manager", "RAGManager"),
        ("rag.rag_manager", "RAGManager"),
        ("rag_manager", "RAGManager"),
        ("rag.rag_manager", None),
    ]
    for module, cls in candidates:
        if cls:
            cls_obj = safe_import(module, cls)
            if cls_obj:
                try:
                    return cls_obj()
                except Exception:
                    return cls_obj
        else:
            mod = safe_import(module)
            if mod:
                return mod
    return None


# -----------------------
# CLI Command implementations
# -----------------------
def cmd_status(args):
    logger.info("PRIMUS CLI: status requested")
    # Basic status
    info = {
        "system_root": str(SYSTEM_ROOT),
        "python": sys.version,
        "cwd": os.getcwd(),
        "log_file": str(LOG_FILE),
    }

    runtime, where = get_runtime()
    info["runtime_loaded"] = bool(runtime)
    info["runtime_source"] = where

    agent_mgr = get_agent_manager()
    info["agent_manager_loaded"] = bool(agent_mgr)

    rag_mgr = get_rag_manager()
    info["rag_manager_loaded"] = bool(rag_mgr)

    pretty_print_object(info)


def cmd_self_test(args):
    logger.info("PRIMUS CLI: self-test requested")
    runtime, where = get_runtime()
    if not runtime:
        logger.error("Runtime not found. Cannot run self-test. (looked in core.primus_runtime)")
        print("Runtime object not available. Ensure core/primus_runtime.py exists and exposes PrimusRuntime().")
        return

    if hasattr(runtime, "run_bootup_test"):
        try:
            res = runtime.run_bootup_test()
            logger.info("Bootup/self-tests completed.")
            pretty_print_object(res)
            return
        except Exception:
            logger.exception("Bootup test failed with exception:")
            show_trace()
            return

    # Fallback: try individual components
    results = {}
    try:
        if hasattr(runtime, "boot_test"):
            results["boot_test"] = runtime.boot_test()
        if hasattr(runtime, "test_agents"):
            results["agents"] = runtime.test_agents()
    except Exception:
        logger.exception("Runtime self-test fallback failed.")
        show_trace()
    pretty_print_object(results)


def cmd_start(args):
    logger.info("PRIMUS CLI: start requested")
    runtime, _ = get_runtime()
    if not runtime:
        print("Runtime not found. Ensure primus runtime exists.")
        return
    if hasattr(runtime, "start"):
        try:
            runtime.start()
            print("PRIMUS runtime started.")
        except Exception:
            logger.exception("Error starting runtime")
            show_trace()
    else:
        print("Runtime does not implement start(). You can still interact with agents directly.")


def cmd_stop(args):
    logger.info("PRIMUS CLI: stop requested")
    runtime, _ = get_runtime()
    if not runtime:
        print("Runtime not found.")
        return
    if hasattr(runtime, "stop"):
        try:
            runtime.stop()
            print("PRIMUS runtime stopped.")
        except Exception:
            logger.exception("Error stopping runtime")
            show_trace()
    else:
        print("Runtime does not implement stop().")


def cmd_agent(args):
    sub = args.agent_command
    am = get_agent_manager()
    if not am:
        print("Agent manager not available. Ensure core/agent_manager.py exists.")
        return

    if sub == "list":
        if hasattr(am, "list_agents"):
            try:
                agents = am.list_agents()
                pretty_print_object(agents)
            except Exception:
                logger.exception("Failed to list agents")
                show_trace()
        else:
            # try attribute 'agents' or inspect filesystem
            if hasattr(am, "agents"):
                pretty_print_object(getattr(am, "agents"))
            else:
                # fallback: scan agents directory
                agents_path = SYSTEM_ROOT / "agents"
                if agents_path.exists():
                    agents = [p.name for p in agents_path.iterdir() if p.is_dir()]
                    pretty_print_object(agents)
                else:
                    print("No agents directory found.")
        return

    if sub == "call":
        # args.agent_name and args.payload_json
        name = args.agent_name
        payload = {}
        if args.payload_json:
            try:
                payload = json.loads(args.payload_json)
            except Exception:
                print("Invalid JSON payload. Provide valid JSON string.")
                return

        # If agent manager has call_agent or dispatch
        if hasattr(am, "call"):
            try:
                res = am.call(name, payload)
                pretty_print_object(res)
                return
            except Exception:
                logger.exception("AgentManager.call failed")
                show_trace()
        if hasattr(am, "call_agent"):
            try:
                res = am.call_agent(name, payload)
                pretty_print_object(res)
                return
            except Exception:
                logger.exception("AgentManager.call_agent failed")
                show_trace()

        # Fallback: try dispatcher via intelligence.dispatcher.dispatcher.Dispatcher
        disp = safe_import("intelligence.dispatcher.dispatcher", "Dispatcher")
        if disp:
            try:
                d = disp()
                res = d.dispatch({"agent": name, **payload})
                pretty_print_object(res)
                return
            except Exception:
                logger.exception("Dispatcher call failed")
                show_trace()

        print("Unable to call agent. Agent manager/dispatcher not found or does not expose call API.")


def cmd_rag(args):
    rag = get_rag_manager()
    if not rag:
        print("RAG manager not available. Ensure rag/rag_manager.py or core/rag_manager.py exists.")
        return

    if args.rag_command == "ingest":
        path = args.path
        if not path:
            print("Provide --path to directory containing documents.")
            return
        # try multiple call signatures
        try:
            if hasattr(rag, "ingest_folder"):
                res = rag.ingest_folder(path, chunk_size=args.chunk_size, overlap=args.overlap, model=args.model)
                pretty_print_object(res)
                return
            if hasattr(rag, "ingest"):
                res = rag.ingest(path)
                pretty_print_object(res)
                return
            # fallback: call rag.ingest.py as script
            script = SYSTEM_ROOT / "rag" / "ingest.py"
            if script.exists():
                os.system(f'python "{script}" --path "{path}"')
                return
            print("RAG ingest: no recognizable API found.")
        except Exception:
            logger.exception("RAG ingest failed")
            show_trace()
        return

    if args.rag_command == "search":
        q = args.query
        if not q:
            print("Provide --query")
            return
        try:
            if hasattr(rag, "search"):
                results = rag.search(q, top_k=args.top_k, model=args.model)
                pretty_print_object(results)
                return
            # fallback to query.py CLI
            query_script = SYSTEM_ROOT / "rag" / "query.py"
            if query_script.exists():
                os.system(f'python "{query_script}" --query "{q}" --model "{args.model}" --top-k {args.top_k}')
                return
            print("RAG search: no recognizable API found.")
        except Exception:
            logger.exception("RAG search failed")
            show_trace()
        return


def cmd_rag_index(args):
    logger.info("PRIMUS CLI: rag-index requested")
    core_mod = safe_import("core")
    rag_index_func = getattr(core_mod, "rag_index_path", None) if core_mod else None

    if not callable(rag_index_func):
        print("rag_index_path not available. Ensure core.rag_index_path exists.")
        return

    try:
        result = rag_index_func(args.path, recursive=bool(args.recursive))
        pretty_print_object(result)
    except Exception:
        logger.exception("RAG index operation failed")
        show_trace()


def cmd_rag_search(args):
    logger.info("PRIMUS CLI: rag-search requested")
    core_mod = safe_import("core")
    rag_search_func = getattr(core_mod, "rag_retrieve", None) if core_mod else None

    if not callable(rag_search_func):
        print("rag_retrieve not available. Ensure core.rag_retrieve exists.")
        return

    try:
        result = rag_search_func(args.index, args.query)
        pretty_print_object(result)
    except Exception:
        logger.exception("RAG search operation failed")
        show_trace()


def cmd_chat(args):
    """
    Single-turn chat when a message is provided; otherwise fallback to REPL.
    """
    runtime, src = get_runtime()
    if not runtime:
        print("Runtime not available. Chat will be local echo only.")
        print("Start runtime first or implement core/primus_runtime.PrimusRuntime")
        return

    if getattr(args, "message", None):
        try:
            if hasattr(runtime, "chat_with_options"):
                reply = runtime.chat_with_options(
                    user_message=args.message,
                    session_id=getattr(args, "session", None),
                    index_name=getattr(args, "index", None),
                    use_rag=bool(getattr(args, "rag", False)),
                    max_tokens=getattr(args, "max_tokens", 256),
                )
            else:
                reply = runtime.chat_once(args.message) if hasattr(runtime, "chat_once") else None
            if reply is None:
                print("Runtime does not expose chat capabilities; no response available.")
                return
            print(f"User: {args.message}")
            print(f"PRIMUS: {reply}")
        except Exception as exc:
            logger.exception("chat command failed")
            print(f"Model backend error: {exc}")
        return

    # Fallback: interactive REPL using any available send method
    send_fn = None
    for name in ("chat_once", "send_message", "send", "handle_input", "ask", "query", "handle"):
        if hasattr(runtime, name):
            send_fn = getattr(runtime, name)
            break

    print("Entering chat REPL. Type '/exit' to quit, '/help' for commands.")
    while True:
        try:
            text = input("You> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting chat.")
            break
        if not text:
            continue
        if text.lower() in ("/exit", "/quit"):
            break
        if text.lower() == "/help":
            print("Commands:\n  /exit, /quit - leave chat\n  /whoami - runtime info")
            continue
        if text.lower() == "/whoami":
            print(f"Runtime source: {src}")
            continue

        if send_fn:
            try:
                res = send_fn(text)
                print("PRIMUS>", res)
            except Exception:
                logger.exception("Chat send failed")
                show_trace()
                print("PRIMUS> (error)")
        else:
            print("PRIMUS>", "(no runtime send method available)")


def cmd_chat_interactive(args):
    """Interactive multi-turn chat with persistent session and optional RAG."""
    runtime, _ = get_runtime()
    if not runtime:
        print("Runtime not available. Chat will be local echo only.")
        print("Start runtime first or implement core/primus_runtime.PrimusRuntime")
        return

    session_id = args.session or str(uuid.uuid4())
    index_name = getattr(args, "index", "docs") or "docs"
    use_rag = bool(getattr(args, "rag", False))
    max_tokens = getattr(args, "max_tokens", 256)

    print(f"Interactive chat started. Session={session_id} | RAG={'on' if use_rag else 'off'} | Index={index_name or 'none'}")
    print("Type '/exit' or '/quit' to leave.")

    while True:
        try:
            text = input("You> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting chat.")
            break

        if not text:
            continue
        if text.lower() in ("/exit", "/quit"):
            break

        try:
            if hasattr(runtime, "chat_with_options"):
                reply = runtime.chat_with_options(
                    user_message=text,
                    session_id=session_id,
                    index_name=index_name,
                    use_rag=use_rag,
                    max_tokens=max_tokens,
                )
            else:
                reply = runtime.chat_once(text) if hasattr(runtime, "chat_once") else None
            if reply is None:
                print("PRIMUS> (no response available; runtime missing chat implementation)")
                continue
            print(f"PRIMUS> {reply}")
        except Exception as exc:
            logger.exception("interactive chat command failed")
            print(f"Model backend error: {exc}")



def cmd_subchats(args):
    runtime, _ = get_runtime()
    if not runtime:
        print("Runtime not available. Ensure primus_runtime exists.")
        return

    if args.subchat_command == "list":
        try:
            subchats = runtime.list_subchats() if hasattr(runtime, "list_subchats") else []
            if not subchats:
                print("[no subchats]")
            else:
                for sid in subchats:
                    print(f"- {sid}")
        except Exception:
            logger.exception("Failed to list subchats")
            show_trace()
        return

    if args.subchat_command == "create":
        owner = "user:local"
        label = args.label
        is_private = bool(args.private)
        try:
            if hasattr(runtime, "create_subchat"):
                subchat_id = runtime.create_subchat(owner=owner, label=label, is_private=is_private)
                print(f"Created subchat {subchat_id} (label='{label}', private={is_private})")
                return
        except Exception:
            logger.exception("Failed to create subchat")
            show_trace()
            return
        print("Runtime does not expose create_subchat().")



def cmd_logs(args):
    lf = LOG_FILE
    if lf.exists():
        print(f"--- Last 200 lines from {lf} ---")
        with open(lf, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()[-200:]
            print("".join(lines))
    else:
        print("No CLI log file found.")



def cmd_debug(args):
    print("Debug info:")
    cmd_status(args)
    print("\nEnvironment PATH and PYTHONPATH (first 3 entries):")
    print("PATH:", os.environ.get("PATH", "").split(os.pathsep)[:3])
    print("PYTHONPATH:", os.environ.get("PYTHONPATH", "").split(os.pathsep)[:3])


def cmd_captains_log(args):
    """Captain's Log Master Root Mode controls (Phase 1)."""

    runtime, _ = get_runtime()
    if not runtime:
        print("Runtime not available. Ensure primus_runtime exists.")
        return

    sub = getattr(args, "cl_command", None)
    if sub == "enter":
        if hasattr(runtime, "enter_captains_log_mode"):
            try:
                runtime.enter_captains_log_mode()
                print("Captain's Log Master Root Mode: ACTIVE")
            except Exception:
                logger.exception("Failed to enter Captain's Log mode")
                show_trace()
        else:
            print("Runtime does not expose enter_captains_log_mode().")
        return

    if sub == "exit":
        if hasattr(runtime, "exit_captains_log_mode"):
            try:
                runtime.exit_captains_log_mode()
                print("Captain's Log Master Root Mode: INACTIVE")
            except Exception:
                logger.exception("Failed to exit Captain's Log mode")
                show_trace()
        else:
            print("Runtime does not expose exit_captains_log_mode().")
        return

    if sub == "status":
        manager = getattr(runtime, "captains_log_manager", None)
        status = None
        if manager and hasattr(manager, "get_status"):
            try:
                status = manager.get_status()
            except Exception:
                logger.exception("Failed to retrieve Captain's Log status")
                show_trace()

        if status is None:
            status = {"status": "unavailable", "mode": "unknown"}

        mode = status.get("mode", "unknown")
        health = status.get("status", "unknown")
        print(f"Captain's Log system : {health.upper()} (mode={mode})")
        return

    print("Unsupported Captain's Log command.")


# -----------------------
# CLI argument parsing
# -----------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="primus", description="PRIMUS OS CLI")
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging verbosity for CLI operations",
    )
    subparsers = parser.add_subparsers(dest="cmd", required=True)

    # status
    p_status = subparsers.add_parser("status", help="Show system status")
    p_status.set_defaults(func=cmd_status)

    # self-test
    p_self = subparsers.add_parser("self-test", help="Run self-tests (boot/agents/checks)")
    p_self.set_defaults(func=cmd_self_test)
    p_self_alt = subparsers.add_parser("selftest", help="Run self-tests (boot/agents/checks)")
    p_self_alt.set_defaults(func=cmd_self_test)

    # start/stop
    p_start = subparsers.add_parser("start", help="Start primus runtime")
    p_start.set_defaults(func=cmd_start)
    p_stop = subparsers.add_parser("stop", help="Stop primus runtime")
    p_stop.set_defaults(func=cmd_stop)

    # agent commands
    p_agent = subparsers.add_parser("agent", help="Agent operations")
    agent_sub = p_agent.add_subparsers(dest="agent_command", required=True)
    agent_list = agent_sub.add_parser("list", help="List available agents")
    agent_list.set_defaults(func=cmd_agent)
    agent_call = agent_sub.add_parser("call", help="Call an agent with payload")
    agent_call.add_argument("agent_name", type=str, help="Agent name (e.g. FileAgent)")
    agent_call.add_argument("payload_json", type=str, nargs="?", default="{}", help='JSON payload string e.g. \'{"action":"ping"}\'')
    agent_call.set_defaults(func=cmd_agent)

    # RAG commands
    p_rag = subparsers.add_parser("rag", help="RAG operations")
    rag_sub = p_rag.add_subparsers(dest="rag_command", required=True)
    rag_ingest = rag_sub.add_parser("ingest", help="Ingest documents into RAG")
    rag_ingest.add_argument("--path", type=str, required=True, help="Path to documents")
    rag_ingest.add_argument("--chunk-size", type=int, default=500)
    rag_ingest.add_argument("--overlap", type=int, default=50)
    rag_ingest.add_argument("--model", type=str, default="all-MiniLM-L6-v2")
    rag_ingest.set_defaults(func=cmd_rag)

    rag_search = rag_sub.add_parser("search", help="Search RAG index")
    rag_search.add_argument("--query", type=str, required=True)
    rag_search.add_argument("--top-k", type=int, default=5)
    rag_search.add_argument("--model", type=str, default="all-MiniLM-L6-v2")
    rag_search.set_defaults(func=cmd_rag)

    # RAG indexing/search (direct helpers)
    p_rag_index = subparsers.add_parser("rag-index", help="Index a path into RAG")
    p_rag_index.add_argument("path", type=str, help="Path to documents or directory")
    p_rag_index.add_argument("--recursive", action="store_true", help="Recursively index directories")
    p_rag_index.set_defaults(func=cmd_rag_index)

    p_rag_search_direct = subparsers.add_parser("rag-search", help="Search a RAG index")
    p_rag_search_direct.add_argument("index", type=str, help="Index name or path")
    p_rag_search_direct.add_argument("query", type=str, help="Search query")
    p_rag_search_direct.set_defaults(func=cmd_rag_search)

    # subchats
    p_subchat = subparsers.add_parser("subchats", help="Subchat operations")
    subchat_sub = p_subchat.add_subparsers(dest="subchat_command", required=True)
    subchat_list = subchat_sub.add_parser("list", help="List subchats")
    subchat_list.set_defaults(func=cmd_subchats)
    subchat_create = subchat_sub.add_parser("create", help="Create a subchat")
    subchat_create.add_argument("--label", required=True, help="Subchat label")
    subchat_create.add_argument("--private", action="store_true", help="Mark subchat private")
    subchat_create.set_defaults(func=cmd_subchats)

    # Captain's Log controls
    p_cl = subparsers.add_parser("cl", help="Captain's Log Master Root Mode controls")
    cl_sub = p_cl.add_subparsers(dest="cl_command", required=True)
    cl_enter = cl_sub.add_parser("enter", help="Enter Captain's Log Master Root Mode")
    cl_enter.set_defaults(func=cmd_captains_log)
    cl_exit = cl_sub.add_parser("exit", help="Exit Captain's Log Master Root Mode")
    cl_exit.set_defaults(func=cmd_captains_log)
    cl_status = cl_sub.add_parser("status", help="Show Captain's Log status")
    cl_status.set_defaults(func=cmd_captains_log)

    # chat
    p_chat = subparsers.add_parser("chat", help="Single-turn chat or interactive REPL if no message is provided")
    p_chat.add_argument("message", nargs="?", help="Optional single-turn message to send to PRIMUS")
    p_chat.add_argument("--session", type=str, help="Optional session identifier to reuse across calls")
    p_chat.add_argument("--index", type=str, default="docs", help="RAG index name to use when --rag is enabled")
    rag_group = p_chat.add_mutually_exclusive_group()
    rag_group.add_argument("--rag", dest="rag", action="store_true", help="Enable RAG context for chat")
    rag_group.add_argument("--no-rag", dest="rag", action="store_false", help="Disable RAG context for chat")
    p_chat.set_defaults(func=cmd_chat, rag=True)
    p_chat.add_argument("--max-tokens", type=int, default=256, help="Maximum tokens for model response")

    # chat-interactive
    p_chat_int = subparsers.add_parser(
        "chat-interactive",
        help="Interactive multi-turn chat with persistent session and optional RAG",
    )
    p_chat_int.add_argument("--session", type=str, help="Optional session identifier to reuse across turns")
    p_chat_int.add_argument("--index", type=str, default="docs", help="RAG index name to use when --rag is enabled")
    rag_group_int = p_chat_int.add_mutually_exclusive_group()
    rag_group_int.add_argument("--rag", dest="rag", action="store_true", help="Enable RAG context for chat")
    rag_group_int.add_argument("--no-rag", dest="rag", action="store_false", help="Disable RAG context for chat")
    p_chat_int.set_defaults(func=cmd_chat_interactive, rag=True)
    p_chat_int.add_argument("--max-tokens", type=int, default=256, help="Maximum tokens for model response")

    # logs
    p_logs = subparsers.add_parser("logs", help="Show recent CLI logs")
    p_logs.set_defaults(func=cmd_logs)

    # debug
    p_debug = subparsers.add_parser("debug", help="Developer debug info")
    p_debug.set_defaults(func=cmd_debug)

    return parser


# -----------------------
# Main
# -----------------------
def main():
    parser = build_parser()
    args = parser.parse_args()
    set_log_level(getattr(args, "log_level", "INFO"))
    try:
        if hasattr(args, "func"):
            args.func(args)
        else:
            parser.print_help()
    except Exception:
        logger.exception("Unhandled exception in primus_cli main")
        show_trace()


if __name__ == "__main__":
    main()
