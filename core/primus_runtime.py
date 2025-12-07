# System/core/primus_runtime.py
#!/usr/bin/env python3
"""
primus_runtime.py

Runtime entrypoint utilities for PRIMUS OS.

Responsibilities:
- Provide a simple CLI for starting PRIMUS runtime modes.
- Integrate Captain's Log secure mode (requires authentication).
- Offer a lightweight interactive loop for Captain's Log sessions.
- Safe imports and helpful error messages if supporting modules are missing.
- Run core security + diagnostic self-tests during startup when requested.

Location (example):
    "C:\\P.R.I.M.U.S OS\\System\\core\\primus_runtime.py"
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import traceback
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------

SYSTEM_ROOT = Path(__file__).resolve().parents[1]  # .../System
PROJECT_ROOT = SYSTEM_ROOT.parent

# Ensure both System/ and repo root are importable regardless of invocation path
for path in (SYSTEM_ROOT, PROJECT_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

SYSTEM_DIR = SYSTEM_ROOT / "System"
if SYSTEM_DIR.exists() and str(SYSTEM_DIR) not in sys.path:
    sys.path.insert(0, str(SYSTEM_DIR))

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

LOG_DIR = SYSTEM_ROOT / "core" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "runtime.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)

logger = logging.getLogger("primus_runtime")

# ---------------------------------------------------------------------------
# Safe imports for Captain's Log and core subsystems
# ---------------------------------------------------------------------------


def _safe_import(module_name: str):
    try:
        return __import__(module_name, fromlist=["*"])
    except Exception:
        try:
            root = Path(__file__).resolve().parents[2]  # repo root
            if str(root) not in sys.path:
                sys.path.insert(0, str(root))
            return __import__(module_name, fromlist=["*"])
        except Exception:
            return None


CAPTAINS_LOG_MODULE = _safe_import("core.captains_log") or _safe_import("captains_log")
CAPTAINS_LOG_AUTH = _safe_import("core.captains_log_auth") or _safe_import("captains_log_auth")

# Security + diagnostics imports (kept lazy-friendly for robustness)
try:
    from diagnostics.selftest import run_selftest as run_core_selftest
except Exception:
    run_core_selftest = None
    logger.warning("diagnostics.selftest not available; self-tests limited.")

try:
    from diagnostics.integrity_checker import run_integrity_check
except Exception:
    run_integrity_check = None
    logger.warning("diagnostics.integrity_checker not available; integrity checks limited.")

try:
    from captains_log.cl_manager import CaptainsLogManager, get_manager as get_captains_log_manager
except Exception:
    CaptainsLogManager = None
    get_captains_log_manager = None
    logger.warning("captains_log.cl_manager not available; Captain's Log manager unavailable.")

try:
    from core.security_gate import SecurityGate, get_security_gate
except Exception:
    SecurityGate = None
    get_security_gate = None
    logger.warning("core.security_gate not available; SecurityGate unavailable.")

try:
    from security.security_layer import get_security_layer
except Exception:
    get_security_layer = None
    logger.warning("security_layer not available; sandbox state will not be inspected.")

try:
    from core.security_enforcer import SecurityEnforcer
except Exception:
    SecurityEnforcer = None
    logger.warning("security_enforcer not available; enforcement layer not initialized.")

try:
    from core.primus_core import PrimusCore, get_primus_core
except Exception:
    PrimusCore = None
    get_primus_core = None
    logger.warning("PrimusCore not available; model/chat and subchat checks limited.")


# ---------------------------------------------------------------------------
# Runtime wrapper
# ---------------------------------------------------------------------------


class PrimusRuntime:
    """Lightweight runtime wrapper that wires security, diagnostics, and core."""

    def __init__(self):
        self.security_layer = get_security_layer() if get_security_layer else None
        self.security_enforcer = SecurityEnforcer.get() if SecurityEnforcer else None
        self.captains_log_manager = (
            get_captains_log_manager() if get_captains_log_manager else None
        )
        self.security_gate = get_security_gate() if get_security_gate else None
        self._core: Optional[PrimusCore] = None

        logger.info(
            "PrimusRuntime initialized (security_layer=%s, security_enforcer=%s)",
            bool(self.security_layer),
            bool(self.security_enforcer),
        )

    # -------------------------
    # Core access
    # -------------------------

    def _ensure_core(self) -> PrimusCore:
        """Ensure a PrimusCore instance is available and initialized."""
        if get_primus_core is None:
            raise RuntimeError("PrimusCore is not available (get_primus_core import failed).")

        if self._core is None:
            logger.info("Creating PrimusCore instance from runtime...")
            self._core = get_primus_core(singleton=True)
            init_status = self._core.initialize()
            logger.info("PrimusCore initialized with status: %s", json.dumps(init_status, indent=2))

        return self._core

    # -------------------------
    # Captain's Log helpers
    # -------------------------

    def enter_captains_log_mode(self) -> None:
        """Request entry into Captain's Log Master Root mode."""

        if not self.captains_log_manager:
            logger.warning("Captain's Log manager unavailable; cannot enter mode.")
            return

        logger.info("PrimusRuntime: enter Captain's Log requested.")
        self.captains_log_manager.enter()

    def exit_captains_log_mode(self) -> None:
        """Request exit from Captain's Log Master Root mode."""

        if not self.captains_log_manager:
            logger.warning("Captain's Log manager unavailable; cannot exit mode.")
            return

        logger.info("PrimusRuntime: exit Captain's Log requested.")
        self.captains_log_manager.exit()

    def is_captains_log_active(self) -> bool:
        """Return whether Captain's Log Master Root mode is active."""

        if not self.captains_log_manager:
            return False

        return self.captains_log_manager.is_active()

    # -------------------------
    # Security-aware startup
    # -------------------------

    def run_security_preflight(self) -> Dict[str, Any]:
        """Return a summary of security configuration and sandbox state."""
        status: Dict[str, Any] = {"security_layer": "missing", "security_enforcer": "missing"}

        if self.security_layer:
            auth_cfg = self.security_layer._config.get("auth", {})  # type: ignore[attr-defined]
            status["security_layer"] = {
                "sandbox_active": self.security_layer.is_sandbox_active(),
                "password_configured": bool(auth_cfg.get("password_hash")),
                "pending_approvals": len(self.security_layer.approval.list_pending()),  # type: ignore[attr-defined]
            }

        if self.security_enforcer:
            policies = self.security_enforcer.policies if hasattr(self.security_enforcer, "policies") else {}
            status["security_enforcer"] = {
                "policies_loaded": bool(policies),
                "pending_approvals": len(self.security_enforcer.get_pending_approvals()),
            }

        return status

    def run_self_tests(self) -> Dict[str, Any]:
        """Run diagnostics + security preflight."""
        results: Dict[str, Any] = {
            "security": {},
            "diagnostics_selftest": None,
            "integrity_check": None,
        }

        try:
            results["security"] = self.run_security_preflight()
        except Exception as exc:  # noqa: BLE001
            results["security"] = {"status": "error", "error": str(exc)}
            logger.exception("Security preflight failed: %s", exc)

        if run_core_selftest:
            try:
                results["diagnostics_selftest"] = run_core_selftest()
            except Exception as exc:  # noqa: BLE001
                results["diagnostics_selftest"] = {"status": "error", "error": str(exc)}
                logger.exception("diagnostics.selftest failed: %s", exc)

        if run_integrity_check:
            try:
                results["integrity_check"] = run_integrity_check()
            except Exception as exc:  # noqa: BLE001
                results["integrity_check"] = {"status": "error", "error": str(exc)}
                logger.exception("integrity_check failed: %s", exc)

        return results

    def start(self) -> None:
        logger.info("PrimusRuntime start requested; running security preflight.")
        preflight = self.run_security_preflight()
        logger.info("Security preflight: %s", preflight)
        start_primus_normal()

    def stop(self) -> None:
        logger.info("PrimusRuntime stop requested (no-op stub).")

    # -------------------------
    # Chat wrapper for CLI
    # -------------------------

    def chat_once(
        self,
        user_message: str,
        session_id: Optional[str] = None,
        use_rag: bool = False,
        rag_index: Optional[str] = None,
        max_tokens: int = 256,
    ) -> str:
        """Runtime-level wrapper for a single chat turn.

        The runtime remains the sole gateway for CLI/GUI callers while
        forwarding all chat configuration to PrimusCore. The runtime itself does
        not implement any chat logic beyond delegation and lightweight logging.
        This docstring is intentionally compact to avoid any parsing ambiguity
        across environments that treat wrapped text differently.
        """

        logger.info(
            "PrimusRuntime.chat_once called (session_id=%s, use_rag=%s, rag_index=%s, max_tokens=%s)",
            session_id,
            use_rag,
            rag_index,
            max_tokens,
        )
        core = self._ensure_core()
        return core.chat(
            user_message=user_message,
            session_id=session_id,
            use_rag=use_rag,
            rag_index=rag_index,
            max_tokens=max_tokens,
        )

    def chat_with_options(
        self,
        user_message: str,
        session_id: Optional[str] = None,
        index_name: Optional[str] = None,
        use_rag: bool = False,
        max_tokens: int = 256,
    ) -> str:
        """
        Bridge helper for CLI and other entrypoints to invoke PrimusCore.chat.

        This keeps runtime as the single adapter layer while allowing callers to
        toggle session reuse and RAG options without reaching into PrimusCore
        directly.
        """

        return self.chat_once(
            user_message=user_message,
            session_id=session_id,
            use_rag=use_rag,
            rag_index=index_name,
            max_tokens=max_tokens,
        )

    # -------------------------
    # Bootup self-test for CLI / --run-bootup-test
    # -------------------------

    def run_bootup_test(self) -> int:
        """
        Run a bootup self-test:
        - Security layer
        - SubChat subsystem (if present)
        - Model backend
        - Core self-test
        Returns an exit code (0 = all good, non-zero = failure).
        """
        logger.info("Bootup self-test requested.")
        ok_all = True

        # Security check
        try:
            security_status = self.run_security_preflight()
            sec_layer = security_status.get("security_layer", {})
            sec_enforcer = security_status.get("security_enforcer", {})

            sec_ok = isinstance(sec_layer, dict) and isinstance(sec_enforcer, dict)
            print(f"Security layer : {'WORKING' if sec_ok else 'FAILED'}")
            logger.info("Bootup Test - Security: %s", security_status)

            if not sec_ok:
                ok_all = False
        except Exception as exc:  # noqa: BLE001
            print(f"Security layer : FAILED ({exc})")
            logger.exception("Bootup Test - Security preflight failed: %s", exc)
            ok_all = False

        # Core + subchats + model checks
        core: Optional[PrimusCore] = None
        try:
            core = self._ensure_core()
        except Exception as exc:  # noqa: BLE001
            print(f"Core initialization : FAILED ({exc})")
            logger.exception("Bootup Test - Core initialization failed: %s", exc)
            ok_all = False

        # Captain's Log status
        try:
            if self.captains_log_manager:
                cl_active = self.captains_log_manager.is_active()
                cl_mode = "captains_log" if cl_active else "normal"
                print(f"Captain's Log system : WORKING (mode={cl_mode})")
                logger.info(
                    "Bootup Test - Captain's Log status: active=%s mode=%s",
                    cl_active,
                    cl_mode,
                )
            else:
                print("Captain's Log system : MISSING (manager unavailable)")
                logger.warning("Bootup Test - Captain's Log manager unavailable.")
                ok_all = False
        except Exception as exc:  # noqa: BLE001
            print(f"Captain's Log system : FAILED ({exc})")
            logger.exception("Bootup Test - Captain's Log check failed: %s", exc)
            ok_all = False

        # Security Gate status
        try:
            if self.security_gate:
                gate_status = self.security_gate.get_status()
                gate_mode = gate_status.get("mode", "unknown")
                net_allowed = gate_status.get("external_network_allowed", "unknown")
                print(
                    "Security Gate      : WORKING (mode=%s, external_network_allowed=%s)"
                    % (gate_mode, net_allowed)
                )
                logger.info("Bootup Test - Security Gate status: %s", gate_status)
            else:
                print("Security Gate      : MISSING (not initialized)")
                logger.warning("Bootup Test - SecurityGate unavailable.")
                ok_all = False
        except Exception as exc:  # noqa: BLE001
            print(f"Security Gate      : FAILED ({exc})")
            logger.exception("Bootup Test - SecurityGate check failed: %s", exc)
            ok_all = False

        # Subchat system
        if core is not None:
            try:
                if core.subchat_loader and core.subchat_security:
                    count = len(core.list_subchats())
                    print(f"SubChat system : WORKING ({count} subchats discovered)")
                    logger.info("Bootup Test - Subchats OK (%d subchats).", count)
                else:
                    print("SubChat system : MISSING (components not available)")
                    logger.warning("Bootup Test - Subchats missing.")
            except Exception as exc:  # noqa: BLE001
                print(f"SubChat system : FAILED ({exc})")
                logger.exception("Bootup Test - Subchats failed: %s", exc)
                ok_all = False

            # Model backend
            try:
                model_ok, model_msg = core.model_status_check()
                print(f"Model backend : {'WORKING' if model_ok else 'FAILED'} ({model_msg})")
                logger.info("Bootup Test - Model backend: ok=%s msg=%s", model_ok, model_msg)
                if not model_ok:
                    ok_all = False
            except Exception as exc:  # noqa: BLE001
                print(f"Model backend : FAILED ({exc})")
                logger.exception("Bootup Test - Model backend check failed: %s", exc)
                ok_all = False

            # Core self-test (optional)
            try:
                st = core.run_self_test()
                logger.info("Bootup Test - Core self-test summary: %s", json.dumps(st, indent=2))
                print("Core self-test : COMPLETED (see logs for details)")
            except Exception as exc:  # noqa: BLE001
                print(f"Core self-test : FAILED ({exc})")
                logger.exception("Bootup Test - Core self-test failed: %s", exc)
                ok_all = False

        # Final summary
        if ok_all:
            print("Bootup Test : ALL CHECKS PASSED.")
            logger.info("Bootup Test completed successfully.")
            return 0

        print("Bootup Test : ONE OR MORE CHECKS FAILED.")
        logger.warning("Bootup Test completed with failures.")
        return 1


# ---------------------------------------------------------------------------
# Normal PRIMUS startup
# ---------------------------------------------------------------------------


def start_primus_normal() -> None:
    """
    Placeholder for normal PRIMUS runtime startup.

    Minimal friendly output + logging; the full UI/engine is handled elsewhere.
    """
    logger.info("Starting PRIMUS (normal mode)...")
    print("PRIMUS runtime starting (normal mode).")
    # Here you would normally load kernel, engine, agents, etc.
    logger.info("PRIMUS runtime started (normal mode).")


# ---------------------------------------------------------------------------
# Captain's Log interactive REPL
# ---------------------------------------------------------------------------


def start_captains_log_interactive(vault: Any) -> None:
    """
    Starts a simple interactive REPL for Captain's Log operations.

    The vault is an instance of the Captains Log handler (passed from module).

    Commands:
      help            - show commands
      list            - list entries
      read <id>       - read entry by id
      write           - create a new entry (multiline; end with a single '.' on a line)
      delete <id>     - delete an entry
      export <id> <file> - export an entry to a plaintext file
      exit / quit     - leave Captain's Log mode
    """
    print("\nEntering Captain's Log (secure sandbox).")
    print("Type 'help' for commands.\n")
    logger.info("Captain's Log interactive session started.")

    try:
        while True:
            try:
                cmd = input("captainslog> ").strip()
            except (KeyboardInterrupt, EOFError):
                print("\nExiting Captain's Log.")
                logger.info("Captain's Log interactive session terminated by user.")
                break

            if not cmd:
                continue

            parts = cmd.split()
            verb = parts[0].lower()

            if verb in ("exit", "quit"):
                print("Closing Captain's Log.")
                logger.info("Captain's Log session closed by user.")
                break

            if verb == "help":
                print(
                    "Commands:\n"
                    "  help            Show this help\n"
                    "  list            List all entries (IDs + meta)\n"
                    "  read <id>       Read entry by id\n"
                    "  write           Create a new entry (end input with a single '.' line)\n"
                    "  delete <id>     Delete entry by id\n"
                    "  export <id> <f> Export entry text to file\n"
                    "  exit / quit     Exit captain's log\n"
                )
                continue

            if verb == "list":
                try:
                    entries = vault.list_entries()
                    if not entries:
                        print("[empty]")
                    else:
                        for e in entries:
                            eid = e.get("id") or e.get("entry_id") or ""
                            ts = e.get("timestamp", "")
                            note = e.get("meta", "")
                            print(f"- {eid} {ts} {note}")
                except Exception as exc:  # noqa: BLE001
                    logger.exception("Error listing entries: %s", exc)
                    print("[ERROR] Could not list entries.")
                continue

            if verb == "read" and len(parts) >= 2:
                eid = parts[1]
                try:
                    text = vault.read_entry(eid)
                    if text is None:
                        print("[not found]")
                    else:
                        print("\n--- ENTRY START ---\n")
                        print(text)
                        print("\n--- ENTRY END ---\n")
                except Exception as exc:  # noqa: BLE001
                    logger.exception("Error reading entry %s: %s", eid, exc)
                    print("[ERROR] Could not read entry.")
                continue

            if verb == "write":
                print("Enter your entry. End with a single '.' on its own line.")
                lines = []
                while True:
                    try:
                        line = input()
                    except (KeyboardInterrupt, EOFError):
                        print("\n[write cancelled]")
                        lines = []
                        break
                    if line.strip() == ".":
                        break
                    lines.append(line)

                if not lines:
                    continue

                body = "\n".join(lines)
                try:
                    eid = vault.create_entry(body)
                    print(f"[saved] id={eid}")
                    logger.info("Captain's Log: created entry %s", eid)
                except Exception as exc:  # noqa: BLE001
                    logger.exception("Error saving entry: %s", exc)
                    print("[ERROR] Could not save entry.")
                continue

            if verb == "delete" and len(parts) >= 2:
                eid = parts[1]
                try:
                    ok = vault.delete_entry(eid)
                    print("[deleted]" if ok else "[not found]")
                except Exception as exc:  # noqa: BLE001
                    logger.exception("Error deleting entry %s: %s", eid, exc)
                    print("[ERROR] Could not delete entry.")
                continue

            if verb == "export" and len(parts) >= 3:
                eid = parts[1]
                outpath = parts[2]
                try:
                    txt = vault.read_entry(eid)
                    if txt is None:
                        print("[not found]")
                    else:
                        with open(outpath, "w", encoding="utf-8") as f:
                            f.write(txt)
                        print(f"[exported] -> {outpath}")
                except Exception as exc:  # noqa: BLE001
                    logger.exception("Error exporting entry %s: %s", eid, exc)
                    print("[ERROR] Could not export entry.")
                continue

            print("[unknown command] Type 'help' for a list of commands.")
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unhandled error in Captain's Log REPL: %s", exc)
        print("[ERROR] Captain's Log encountered an internal error. See runtime log.")


def run_captains_log_mode(interactive: bool = True, password: Optional[str] = None) -> None:
    """
    Authenticate and open Captain's Log vault.

    - Uses captains_log_auth to authenticate (password/PIN/security questions).
    - Uses captains_log to mount/open vault and return a vault object.
    """
    if CAPTAINS_LOG_AUTH is None or CAPTAINS_LOG_MODULE is None:
        logger.error("Captain's Log modules not found (captains_log/auth). Cannot enter mode.")
        print("[ERROR] Captain's Log is not available. Missing modules.")
        return

    try:
        auth = CAPTAINS_LOG_AUTH
        logmod = CAPTAINS_LOG_MODULE

        authenticate = getattr(auth, "authenticate", None) or getattr(auth, "verify_password", None)
        if authenticate is None:
            logger.error("Authentication function not found in captains_log_auth module.")
            print("[ERROR] Authentication subsystem unavailable.")
            return

        if password:
            ok, info = authenticate(password=password, non_interactive=True)
        else:
            ok, info = authenticate()

        if not ok:
            logger.warning("Captain's Log auth failed.")
            print("[AUTH FAILED] Unable to authenticate.")
            return

        logger.info("Captain's Log auth succeeded. Opening vault...")

        open_vault_fn = getattr(logmod, "open_vault", None) or getattr(logmod, "CaptainsLog", None)
        if open_vault_fn is None:
            logger.error("Captains Log opening function/class not found.")
            print("[ERROR] Captain's Log vault handler missing.")
            return

        try:
            if callable(open_vault_fn):
                vault = open_vault_fn()
            else:
                vault = None
        except TypeError:
            vault = open_vault_fn()

        if vault is None:
            logger.error("Could not instantiate/open Captain's Log vault.")
            print("[ERROR] Captain's Log vault could not be opened.")
            return

        if interactive:
            start_captains_log_interactive(vault)
        else:
            print("[Captain's Log] Vault opened successfully.")
            logger.info("Captain's Log vault opened (non-interactive).")
    except Exception as exc:  # noqa: BLE001
        logger.exception("Error during Captain's Log mode: %s", exc)
        print("[ERROR] Captain's Log mode failed. See runtime log.")


# ---------------------------------------------------------------------------
# Argument parsing and entrypoint
# ---------------------------------------------------------------------------


def parse_args_and_run() -> None:
    parser = argparse.ArgumentParser(prog="primus_runtime", description="PRIMUS runtime helper")
    parser.add_argument(
        "--mode",
        choices=["normal", "captainslog"],
        default="normal",
        help="Runtime mode to launch",
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Run non-interactive / headless (where supported)",
    )
    parser.add_argument(
        "--password",
        type=str,
        help="(Optional) password/PIN for non-interactive Captain's Log auth",
    )
    parser.add_argument(
        "--run-bootup-test",
        action="store_true",
        help="Run boot + diagnostics self-tests and exit",
    )

    args = parser.parse_args()
    logger.info("primus_runtime invoked with args: %s", args)

    runtime = PrimusRuntime()

    # Bootup self-test overrides normal startup
    if args.run_bootup_test:
        exit_code = runtime.run_bootup_test()
        sys.exit(exit_code)

    if args.mode == "normal":
        runtime.start()
        return

    if args.mode == "captainslog":
        # Run security preflight before entering sandboxed Captain's Log
        runtime.run_security_preflight()
        run_captains_log_mode(interactive=(not args.non_interactive), password=args.password)
        return


if __name__ == "__main__":
    try:
        parse_args_and_run()
    except Exception as e:  # noqa: BLE001
        logger.exception("Uncaught exception in primus_runtime: %s", e)
        print("Critical runtime error. See logs for details.")
        traceback.print_exc()