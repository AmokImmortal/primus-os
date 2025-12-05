# primus_master.py
"""
PRIMUS Master Entry Script
Milestone 2 — Boot + Dispatcher Test Harness
"""

import argparse
import os
import sys

# Allow imports relative to System root
ROOT = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
if ROOT not in sys.path:
    sys.path.append(ROOT)

from core.boot.boot import boot_system
from intelligence.dispatcher.dispatcher import Dispatcher
from intelligence.dispatcher.bridge import Bridge


def run_test_boot():
    print("Running PRIMUS boot test...")

    # ---- 1. Boot system ----
    boot_info = boot_system()
    if boot_info.get("status") != "ok":
        print("Boot FAILED:", boot_info)
        return

    print(f"[boot] Boot completed. Paths loaded from {boot_info['config_path']}")
    print("PRIMUS master boot OK — configs loaded")

    # ---- 2. Test dispatcher ----
    dispatcher = Dispatcher()
    result = dispatcher.dispatch({
    "agent": "FileAgent",
    "action": "ping"
})
    print("Dispatcher test result:", result)

    # ---- 3. Test bridge -> agent ----
    bridge = Bridge()
    agent_result = bridge.send("FileAgent", {"action": "ping"})
    print("Bridge -> FileAgent result:", agent_result)

    # ---- 4. Final evaluation ----
    if (result.get("status") == "ok"
        and agent_result.get("status") == "ok"):
        print("All PRIMUS Milestone 2 tests PASSED.")
    else:
        print("One or more checks failed. Inspect output above.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--test-boot", action="store_true",
                        help="Run PRIMUS Milestone 2 boot sequence test")
    args = parser.parse_args()

    if args.test_boot:
        run_test_boot()
    else:
        print("PRIMUS Master loaded. No mode selected.")


if __name__ == "__main__":
    main()