#!/usr/bin/env python3
"""
core/primus_runtime.py

PRIMUS runtime wrapper and CLI entry helper.

Responsibilities:
- Set up import paths and logging.
- Provide a thin PrimusRuntime class that owns a PrimusCore instance.
- Expose:
    - start()          – normal runtime bootstrap (stub for now).
    - run_bootup_test() – core + model + RAG + security self-check.
    - chat_once()      – single-turn chat for primus_cli.py.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import traceback
from pathlib import Path
from typing import Any, Dict, Optional

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------

# This file lives at .../System/core/primus_runtime.py
SYSTEM_ROOT = Path(__file__).resolve().parent.parent  # .../System
PROJECT_ROOT = SYSTEM_ROOT.parent

for p in (str(SYSTEM_ROOT), str(PROJECT_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

SYSTEM_DIR = SYSTEM_ROOT / "System"
if SYSTEM_DIR.exists() and str(SYSTEM_DIR) not in sys.path:
    sys.path.insert(0, str(SYSTEM_DIR))

SYSTEM_DIR = SYSTEM_ROOT / "System"
if SYSTEM_DIR.exists() and str(SYSTEM_DIR) not in sys.path:
    sys.path.insert(0, str(SYSTEM_DIR))

SYSTEM_DIR = SYSTEM_ROOT / "System"
if SYSTEM_DIR.exists() and str(SYSTEM_DIR) not in sys.path:
    sys.path.insert(0, str(SYSTEM_DIR))

SYSTEM_DIR = SYSTEM_ROOT / "System"
if SYSTEM_DIR.exists() and str(SYSTEM_DIR) not in sys.path:
    sys.path.insert(0, str(SYSTEM_DIR))

SYSTEM_DIR = SYSTEM_ROOT / "System"
if SYSTEM_DIR.exists() and str(SYSTEM_DIR) not in sys.path:
    sys.path.insert(0, str(SYSTEM_DIR))

SYSTEM_DIR = SYSTEM_ROOT / "System"
if SYSTEM_DIR.exists() and str(SYSTEM_DIR) not in sys.path:
    sys.path.insert(0, str(SYSTEM_DIR))

SYSTEM_DIR = SYSTEM_ROOT / "System"
if SYSTEM_DIR.exists() and str(SYSTEM_DIR) not in sys.path:
    sys.path.insert(0, str(SYSTEM_DIR))

SYSTEM_DIR = SYSTEM_ROOT / "System"
if SYSTEM_DIR.exists() and str(SYSTEM_DIR) not in sys.path:
    sys.path.insert(0, str(SYSTEM_DIR))

SYSTEM_DIR = SYSTEM_ROOT / "System"
if SYSTEM_DIR.exists() and str(SYSTEM_DIR) not in sys.path:
    sys.path.insert(0, str(SYSTEM_DIR))

SYSTEM_DIR = SYSTEM_ROOT / "System"
if SYSTEM_DIR.exists() and str(SYSTEM_DIR) not in sys.path:
    sys.path.insert(0, str(SYSTEM_DIR))

SYSTEM_DIR = SYSTEM_ROOT / "System"
if SYSTEM_DIR.exists() and str(SYSTEM_DIR) not in sys.path:
    sys.path.insert(0, str(SYSTEM_DIR))

SYSTEM_DIR = SYSTEM_ROOT / "System"
if SYSTEM_DIR.exists() and str(SYSTEM_DIR) not in sys.path:
    sys.path.insert(0, str(SYSTEM_DIR))

SYSTEM_DIR = SYSTEM_ROOT / "System"
if SYSTEM_DIR.exists() and str(SYSTEM_DIR) not in sys.path:
    sys.path.insert(0, str(SYSTEM_DIR))

SYSTEM_DIR = SYSTEM_ROOT / "System"
if SYSTEM_DIR.exists() and str(SYSTEM_DIR) not in sys.path:
    sys.path.insert(0, str(SYSTEM_DIR))

SYSTEM_DIR = SYSTEM_ROOT / "System"
if SYSTEM_DIR.exists() and str(SYSTEM_DIR) not in sys.path:
    sys.path.insert(0, str(SYSTEM_DIR))

SYSTEM_DIR = SYSTEM_ROOT / "System"
if SYSTEM_DIR.exists() and str(SYSTEM_DIR) not in sys.path:
    sys.path.insert(0, str(SYSTEM_DIR))

SYSTEM_DIR = SYSTEM_ROOT / "System"
if SYSTEM_DIR.exists() and str(SYSTEM_DIR) not in sys.path:
    sys.path.insert(0, str(SYSTEM_DIR))

# ---------------------------------------------------------------------------
# Logging
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
# Optional imports (PrimusCore, security, captain’s log)
# ---------------------------------------------------------------------------

# PrimusCore (required for core system)
try:
    from core.primus_core import PrimusCore
except Exception as exc:  # noqa: BLE001
    PrimusCore = None  # type: ignore[assignment]
    logger.warning("PrimusCore import failed in primus_runtime: %s", exc)

# Security layer (optional)
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
    logger.info("security_layer not available; security preflight limited.")

# Security enforcer (optional)
try:
    from core.security_enforcer import SecurityEnforcer
except Exception:
    SecurityEnforcer = None
    logger.info("SecurityEnforcer not available; enforcement checks disabled.")

# Captain's Log manager (optional)
try:
    from captains_log.cl_manager import CaptainsLogManager, get_manager as get_captains_log_manager
except Exception:
    CaptainsLogManager = None
    get_captains_log_manager = None
    logger.info("captains_log.cl_manager not available; Captain's Log checks disabled.")

# Security Gate (optional)
try:
    from core.security_gate import SecurityGate, get_security_gate
except Exception:
    SecurityGate = None
    get_security_gate = None
    logger.info("core.security_gate not available; external network gate checks disabled.")


# ---------------------------------------------------------------------------
# PrimusRuntime
# ---------------------------------------------------------------------------


class PrimusRuntime:
    """
    Lightweight runtime wrapper around PrimusCore and security-related helpers.
    """

    def __init__(self) -> None:
        self.system_root: Path = SYSTEM_ROOT
        self._core: Optional[PrimusCore] = None  # type: ignore[type-arg]

        # Optional helpers
        self.security_layer = get_security_layer() if get_security_layer else None
        self.security_enforcer = SecurityEnforcer.get() if SecurityEnforcer else None  # type: ignore[union-attr]
        self.captains_log_manager = (
            get_captains_log_manager() if get_captains_log_manager else None
        )
        self.security_gate = get_security_gate() if get_security_gate else None

        logger.info("PrimusRuntime initialized.")

    # ------------------------------------------------------------------ #
    # Core access                                                        #
    # ------------------------------------------------------------------ #

    def _ensure_core(self) -> "PrimusCore":
        """
        Lazily construct and initialize a PrimusCore instance.
        """
        if PrimusCore is None:
            raise RuntimeError("PrimusCore is not available (import failed in primus_runtime).")

        if self._core is None:
            logger.info("Creating PrimusCore instance from PrimusRuntime...")
            core = PrimusCore(system_root=self.system_root)
            core.initialize()
            self._core = core
            logger.info("PrimusCore instance created and initialized.")

        return self._core

    # ------------------------------------------------------------------ #
    # Simple lifecycle hooks                                             #
    # ------------------------------------------------------------------ #

    def start(self) -> None:
        """
        Placeholder normal startup. For now, just ensures core is initialized.
        """
        logger.info("PrimusRuntime.start() called; ensuring core is ready.")
        core = self._ensure_core()
        logger.info("PrimusCore ready: %s", core)

    def stop(self) -> None:
        """
        Placeholder shutdown hook (no-op for now).
        """
        logger.info("PrimusRuntime.stop() called; no-op shutdown.")

    # ------------------------------------------------------------------ #
    # Chat wrapper for primus_cli.py                                     #
    # ------------------------------------------------------------------ #

    def chat_once(self, user_message: str) -> str:
        """
        Single-turn chat wrapper used by primus_cli.py.

        Delegates to PrimusCore.chat_once if present; otherwise falls back
        to using the underlying ModelManager directly.
        """
    def chat_once(self, user_message: str) -> str:
        """
        Runtime-level wrapper for a single chat turn with optional session + RAG.
        """
        # existing code...

        # Preferred: PrimusCore.chat_once API
        core = self._ensure_core()
        chat_fn = getattr(core, "chat_once", None)
        if callable(chat_fn):
            logger.info("chat_once: delegating to PrimusCore.chat_once (len=%d)", len(user_message))
            reply = chat_fn(user_message)
            logger.info("chat_once: PrimusCore.chat_once returned reply len=%d", len(reply))
            return reply

        # Fallback: use model_manager.generate for simple completion
        model_manager = getattr(core, "model_manager", None)
        if model_manager is None:
            raise RuntimeError("ModelManager is not available on PrimusCore; cannot chat.")

        prompt = f"User: {user_message}\nAssistant:"
        logger.info("chat_once: using ModelManager.generate directly (len=%d)", len(user_message))
        reply = model_manager.generate(prompt, max_tokens=256)
        logger.info("chat_once: ModelManager.generate returned reply len=%d", len(reply))
        return reply

    # ------------------------------------------------------------------ #
    # Bootup self-test                                                   #
    # ------------------------------------------------------------------ #

    def _security_preflight(self) -> Dict[str, Any]:
        """
        Gather a small, structured snapshot of security state.
        """
        status: Dict[str, Any] = {
            "security_layer": None,
            "security_enforcer": None,
        }

        if self.security_layer:
            try:
                auth_cfg = getattr(self.security_layer, "_config", {}).get("auth", {})  # type: ignore[union-attr]
                status["security_layer"] = {
                    "sandbox_active": self.security_layer.is_sandbox_active(),  # type: ignore[union-attr]
                    "password_configured": bool(auth_cfg.get("password_hash")),
                    "pending_approvals": len(self.security_layer.approval.list_pending()),  # type: ignore[union-attr]
                }
            except Exception as exc:  # noqa: BLE001
                logger.exception("Security layer preflight failed: %s", exc)
                status["security_layer"] = {"error": str(exc)}

        if self.security_enforcer:
            try:
                policies = getattr(self.security_enforcer, "policies", {})
                pending = self.security_enforcer.get_pending_approvals()  # type: ignore[union-attr]
                status["security_enforcer"] = {
                    "policies_loaded": bool(policies),
                    "pending_approvals": len(pending),
                }
            except Exception as exc:  # noqa: BLE001
                logger.exception("Security enforcer preflight failed: %s", exc)
                status["security_enforcer"] = {"error": str(exc)}

        return status

    def run_bootup_test(self) -> int:
        """
        Bootup self-test for CLI:

        - Security layer + enforcer snapshot.
        - PrimusCore initialization.
        - Model backend presence + optional status.
        - RAG embedder presence.
        - Subchat subsystem presence.
        """
        logger.info("Bootup self-test requested.")
        all_ok = True

        # --- Security snapshot ------------------------------------------------
        try:
            sec_status = self._security_preflight()
            sec_layer_ok = isinstance(sec_status.get("security_layer"), dict)
            sec_enf_ok = isinstance(sec_status.get("security_enforcer"), dict)
            sec_ok = sec_layer_ok and sec_enf_ok

            print(f"Security layer : {'WORKING' if sec_ok else 'DEGRADED'}")
            logger.info("Bootup Test - Security snapshot: %s", json.dumps(sec_status, indent=2))
        except Exception as exc:  # noqa: BLE001
            print(f"Security layer : FAILED ({exc})")
            logger.exception("Bootup Test - Security snapshot failed: %s", exc)
            all_ok = False

        # --- Core / PrimusCore -------------------------------------------------
        core: Optional[PrimusCore] = None  # type: ignore[type-arg]
        try:
            core = self._ensure_core()
            print("Core system : WORKING (PrimusCore initialized)")
            logger.info("Bootup Test - Core system initialized successfully.")
        except Exception as exc:  # noqa: BLE001
            print(f"Core system : FAILED ({exc})")
            logger.exception("Bootup Test - Core initialization failed: %s", exc)
            all_ok = False

        # If core is present, run deeper checks
        if core is not None:
            # --- RAG / embedder ------------------------------------------------
            try:
                # NOTE: PrimusCore now exposes rag_embedder instead of 'embedder'
                embedder = getattr(core, "rag_embedder", None)
                if embedder is not None:
                    print("RAG embedder : WORKING")
                    logger.info("Bootup Test - RAG embedder present.")
                else:
                    print("RAG embedder : MISSING")
                    logger.warning("Bootup Test - RAG embedder missing (rag_embedder is None).")
            except Exception as exc:  # noqa: BLE001
                print(f"RAG embedder : FAILED ({exc})")
                logger.exception("Bootup Test - RAG embedder check failed: %s", exc)
                all_ok = False

            # --- Subchat subsystem --------------------------------------------
            try:
                subchat_loader = getattr(core, "subchat_loader", None)
                if subchat_loader is not None:
                    subchats = core.list_subchats() if hasattr(core, "list_subchats") else []
                    print(f"SubChat system : WORKING ({len(subchats)} subchats discovered)")
                    logger.info("Bootup Test - Subchats OK (%d subchats).", len(subchats))
                else:
                    print("SubChat system : MISSING (loader not configured)")
                    logger.warning("Bootup Test - Subchats loader missing.")
            except Exception as exc:  # noqa: BLE001
                print(f"SubChat system : FAILED ({exc})")
                logger.exception("Bootup Test - Subchats check failed: %s", exc)
                all_ok = False

            # --- Model backend -------------------------------------------------
            try:
                model_manager = getattr(core, "model_manager", None)
                if model_manager is None:
                    print("Model backend : FAILED (ModelManager missing)")
                    logger.warning("Bootup Test - ModelManager missing.")
                    all_ok = False
                else:
                    status_fn = getattr(model_manager, "get_backend_status", None)
                    if callable(status_fn):
                        ok_flag, msg = status_fn()
                        print(f"Model backend : {'WORKING' if ok_flag else 'FAILED'} ({msg})")
                        logger.info(
                            "Bootup Test - Model backend status: ok=%s msg=%s", ok_flag, msg
                        )
                        if not ok_flag:
                            all_ok = False
                    else:
                        print("Model backend : UNKNOWN (no status API)")
                        logger.warning(
                            "Bootup Test - ModelManager has no get_backend_status(); reporting UNKNOWN."
                        )
            except Exception as exc:  # noqa: BLE001
                print(f"Model backend : FAILED ({exc})")
                logger.exception("Bootup Test - Model backend check failed: %s", exc)
                all_ok = False

            # --- Captain's Log status -----------------------------------------
            try:
                if self.captains_log_manager:
                    active = self.captains_log_manager.is_active()
                    mode = "captains_log" if active else "normal"
                    print(f"Captain's Log system : WORKING (mode={mode})")
                    logger.info(
                        "Bootup Test - Captain's Log status: active=%s mode=%s", active, mode
                    )
                else:
                    print("Captain's Log system : MISSING (manager unavailable)")
                    logger.warning("Bootup Test - Captain's Log manager unavailable.")
            except Exception as exc:  # noqa: BLE001
                print(f"Captain's Log system : FAILED ({exc})")
                logger.exception("Bootup Test - Captain's Log check failed: %s", exc)
                all_ok = False

            # --- Security Gate status -----------------------------------------
            try:
                if self.security_gate:
                    gate_status = self.security_gate.get_status()
                    mode = gate_status.get("mode", "unknown")
                    net = gate_status.get("external_network_allowed", "unknown")
                    print(f"Security Gate      : WORKING (mode={mode}, external_network_allowed={net})")
                    logger.info("Bootup Test - Security Gate status: %s", gate_status)
                else:
                    print("Security Gate      : MISSING (not initialized)")
                    logger.warning("Bootup Test - SecurityGate unavailable.")
            except Exception as exc:  # noqa: BLE001
                print(f"Security Gate      : FAILED ({exc})")
                logger.exception("Bootup Test - SecurityGate check failed: %s", exc)
                all_ok = False

            # --- Core self-test -----------------------------------------------
            try:
                selftest_fn = getattr(core, "run_self_test", None)
                if callable(selftest_fn):
                    summary = selftest_fn()
                    logger.info(
                        "Bootup Test - Core self-test summary: %s",
                        json.dumps(summary, indent=2),
                    )
                    print("Core self-test : COMPLETED (see logs for details)")
                else:
                    print("Core self-test : SKIPPED (no run_self_test API)")
                    logger.info("Bootup Test - Core self-test skipped; no API.")
            except Exception as exc:  # noqa: BLE001
                print(f"Core self-test : FAILED ({exc})")
                logger.exception("Bootup Test - Core self-test failed: %s", exc)
                all_ok = False

        # Final summary
        if all_ok:
            print("Bootup Test : ALL CHECKS PASSED.")
            logger.info("Bootup Test completed successfully.")
            return 0

        print("Bootup Test : ONE OR MORE CHECKS FAILED.")
        logger.warning("Bootup Test completed with failures.")
        return 1


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="primus_runtime",
        description="PRIMUS runtime helper and bootup self-test",
    )
    parser.add_argument(
        "--run-bootup-test",
        action="store_true",
        help="Run bootup diagnostics and exit",
    )
    parser.add_argument(
        "--mode",
        choices=["normal"],
        default="normal",
        help="Runtime mode (normal only for now; Captain's Log has its own CLI entry)",
    )
    parser.add_argument(
        "--message",
        type=str,
        help="Optional single-turn chat message (primarily for debugging)",
    )
    return parser


def main() -> None:
    parser = _build_arg_parser()
    args = parser.parse_args()
    logger.info("primus_runtime invoked with args: %s", args)

    runtime = PrimusRuntime()

    if args.run_bootup_test:
        code = runtime.run_bootup_test()
        sys.exit(code)

    if args.message:
        try:
            reply = runtime.chat_once(args.message)
            print(reply)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Error during chat_once: %s", exc)
            print(f"[ERROR] chat_once failed: {exc}")
        return

    # Default normal startup
    if args.mode == "normal":
        runtime.start()
        return


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Uncaught exception in primus_runtime main: %s", exc)
        print("Critical runtime error. See logs for details.")
        traceback.print_exc()
