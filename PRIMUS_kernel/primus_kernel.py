# primus_kernel.py
"""
PRIMUS Kernel (Milestone 3)

This is the minimal kernel controller for PRIMUS OS.
Responsibilities:
- Load boot information
- Initialize Dispatcher and Bridge
- Provide a simple API to execute and route tasks
- Basic operational logging

Usage:
    python PRIMUS_kernel\primus_kernel.py --test-kernel
"""

import os
import sys
import json
from datetime import datetime
from pathlib import Path

# Ensure System root is on sys.path so imports work from anywhere
SYSTEM_ROOT = Path(__file__).resolve().parents[1]  # .../System
if str(SYSTEM_ROOT) not in sys.path:
    sys.path.insert(0, str(SYSTEM_ROOT))

# Imports from the project
try:
    from core.boot.boot import boot_system
    from intelligence.dispatcher.dispatcher import Dispatcher
    from intelligence.dispatcher.bridge import Bridge
except Exception as e:
    # If imports fail, surface a clear error but do not crash silently
    raise ImportError(f"[primus_kernel] Failed to import core modules: {e}")


# ---- Logging helpers ----
LOG_DIR = SYSTEM_ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
KERNEL_LOG = LOG_DIR / "kernel.log"


def kernel_log(message: str):
    """Append a timestamped message to the kernel log file."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = f"[{ts}] {message}\n"
    try:
        with open(KERNEL_LOG, "a", encoding="utf-8") as f:
            f.write(entry)
    except Exception:
        # Last-resort print if logging fails
        print("[primus_kernel] Failed to write to kernel.log")


# ---- Kernel class ----
class PrimusKernel:
    def __init__(self):
        self.boot_info = None
        self.dispatcher = None
        self.bridge = None
        self.started = False

    def boot(self):
        """Run boot loader and initialize subsystems."""
        kernel_log("Boot started")
        self.boot_info = boot_system()
        if not isinstance(self.boot_info, dict) or self.boot_info.get("status") != "ok":
            kernel_log(f"Boot failed: {self.boot_info}")
            raise RuntimeError(f"Boot failed: {self.boot_info}")

        kernel_log(f"Boot successful. Config: {self.boot_info.get('config_path')}")
        # Instantiate dispatcher and bridge
        self.dispatcher = Dispatcher()
        self.bridge = Bridge()
        self.started = True
        kernel_log("Subsystems initialized (Dispatcher, Bridge)")

    def execute_task(self, task: dict):
        """
        Main entry to execute a task.

        Task format (Milestone 3 simple standard):
        {
            "source": "user" | "system" | "agent",
            "agent": "FileAgent",           # which agent/folder to use
            "action": "ping" | "read" | ...,
            "data": { ... }                # optional payload
        }

        Returns result dict from agent or dispatcher error dict.
        """
        if not self.started:
            return {"status": "error", "error": "Kernel not started"}

        # Basic validation
        if not isinstance(task, dict):
            return {"status": "error", "error": "Task must be a dict"}

        agent = task.get("agent")
        action = task.get("action")
        data = task.get("data", {})

        if not agent or not action:
            return {"status": "error", "error": "Task missing 'agent' or 'action'"}

        kernel_log(f"Executing task -> agent: {agent}, action: {action}, data_keys: {list(data.keys())}")

        # Use dispatcher/bridge as the routing mechanism:
        # For direct agent calls we will use bridge.send (bridge handles module import)
        try:
            result = self.bridge.send(agent, {"action": action, "data": data})
        except Exception as e:
            kernel_log(f"Exception while calling bridge: {e}")
            return {"status": "error", "error": f"Bridge exception: {e}"}

        kernel_log(f"Task result: {json.dumps(result) if isinstance(result, dict) else str(result)}")
        return result

    def route_system_command(self, cmd: str, params: dict = None):
        """
        Minimal system command router for kernel-level commands.
        Example commands:
            - "status" -> returns boot & subsystem status
            - "list_agents" -> (simple file-based listing of agents)
        """
        params = params or {}
        cmd = cmd.lower().strip()

        if cmd == "status":
            return {
                "status": "ok" if self.started else "stopped",
                "boot_info": self.boot_info.get("paths") if self.boot_info else None
            }

        if cmd == "list_agents":
            agents_dir = SYSTEM_ROOT / "agents"
            if not agents_dir.exists():
                return {"status": "error", "error": "agents folder missing"}
            agents = []
            for p in agents_dir.iterdir():
                if p.is_dir():
                    agents.append(p.name)
            return {"status": "ok", "agents": agents}

        return {"status": "error", "error": f"Unknown system command: {cmd}"}


# ---- Test harness / CLI integration ----
def run_kernel_tests():
    """
    A set of small sanity checks to validate kernel <-> dispatcher <-> agents.
    Uses FileAgent ping/read as working examples.
    """
    print("PRIMUS Kernel — running self-tests...")
    kernel = PrimusKernel()
    try:
        kernel.boot()
    except Exception as e:
        print("Boot failed:", e)
        return

    print("Boot OK")

    # Test 1: ping FileAgent through kernel
    t1 = {"source": "user", "agent": "FileAgent", "action": "ping", "data": {}}
    r1 = kernel.execute_task(t1)
    print("FileAgent ping result:", r1)

    # Test 2: list agents via system command
    r2 = kernel.route_system_command("list_agents")
    print("List agents:", r2)

    # Test 3: status
    r3 = kernel.route_system_command("status")
    print("Kernel status:", r3)

    print("Kernel self-tests complete.")
    kernel_log("Kernel self-tests completed successfully.")


# CLI entrypoint
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="PRIMUS Kernel (Milestone 3)")
    parser.add_argument("--test-kernel", action="store_true", help="Run kernel self-tests")
    args = parser.parse_args()

    if args.test_kernel:
        run_kernel_tests()
    else:
        print("PRIMUS Kernel module. Use --test-kernel to run checks.")