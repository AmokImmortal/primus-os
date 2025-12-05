"""
Compatibility wrapper so running `python System/core/primus_runtime.py`
from inside the System directory still launches the actual runtime.
"""
from __future__ import annotations
import runpy
from pathlib import Path

def main() -> None:
    target = Path(__file__).resolve().parent.parent.parent / "core" / "primus_runtime.py"
    runpy.run_path(str(target), run_name="__main__")

if __name__ == "__main__":
    main()
