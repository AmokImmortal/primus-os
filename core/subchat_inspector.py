Subchat Inspector
-----------------
Utilities to inspect, validate, summarize and export reports for subchats.
Designed to be safe (read-only by default) and lightweight so it can run on
development machines and inside the PRIMUS environment.

Location example:
C:\P.R.I.M.U.S OS\System\core\subchat_inspector.py

Functions:
- list_subchats() -> list of available subchat ids / folders
- inspect(subchat_id) -> dict with metadata, stats, sample messages
- validate(subchat_id) -> dict with validation results (missing files, schema issues)
- summarize(subchat_id, max_messages=5) -> short text summary
- export_report(subchat_id, out_path) -> writes JSON report to out_path

CLI:
- run from the System root: python -m core.subchat_inspector --list
- or: python core/subchat_inspector.py --inspect <id> --export report.json
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

# Setup basic logger for the module
logger = logging.getLogger("subchat_inspector")
if not logger.handlers:
    handler = logging.StreamHandler()
    fmt = logging.Formatter("[subchat_inspector] %(levelname)s: %(message)s")
    handler.setFormatter(fmt)
    logger.addHandler(handler)
logger.setLevel(logging.INFO)

# Paths
CORE_DIR = Path(__file__).resolve().parents[1]  # .../System/core
SYSTEM_ROOT = CORE_DIR.parent  # .../System
SUBCHAT_ROOT = SYSTEM_ROOT / "core" / "sub_chats"  # default directory for subchats


# --- Helpers -------------------------------------------------------------
def _read_json(path: Path) -> Optional[Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except Exception as e:
        logger.debug("Failed to read JSON %s: %s", path, e)
        return None


def _safe_list_dir(path: Path) -> List[Path]:
    if not path.exists() or not path.is_dir():
        return []
    return [p for p in path.iterdir() if p.is_dir()]


# --- Core functionality --------------------------------------------------
def list_subchats(root: Optional[Path] = None) -> List[str]:
    """Return list of subchat folder names (ids)."""
    root = root or SUBCHAT_ROOT
    folders = _safe_list_dir(root)
    return [f.name for f in sorted(folders)]


def _expected_files() -> List[str]:
    """
    The expected files for a subchat:
      - conversation.json   (list of messages)
      - metadata.json       (subchat metadata: created_at, participants, privacy, tags)
      - state.json (optional) current runtime state/snapshot
    """
    return ["conversation.json", "metadata.json"]


def validate(subchat_id: str, root: Optional[Path] = None) -> Dict[str, Any]:
    """
    Validate presence and basic schema of a subchat.
    Returns a dict with status and list of issues (empty if ok).
    """
    root = root or SUBCHAT_ROOT
    sc_path = root / subchat_id
    issues: List[str] = []

    if not sc_path.exists() or not sc_path.is_dir():
        return {"status": "error", "issues": [f"Subchat folder '{subchat_id}' not found"]}

    # Check required files
    for fname in _expected_files():
        if not (sc_path / fname).exists():
            issues.append(f"Missing file: {fname}")

    # Validate conversation.json schema (simple checks)
    convo = _read_json(sc_path / "conversation.json")
    if convo is None:
        issues.append("conversation.json unreadable or missing")
    else:
        if not isinstance(convo, list):
            issues.append("conversation.json must be a list of message objects")
        else:
            # check a few items
            for i, m in enumerate(convo[:5]):
                if not isinstance(m, dict):
                    issues.append(f"conversation.json message {i} not an object")
                    break
                if "timestamp" not in m or "sender" not in m or "text" not in m:
                    issues.append(f"conversation.json message {i} missing required keys")
                    break

    # Validate metadata.json
    meta = _read_json(sc_path / "metadata.json")
    if meta is None:
        issues.append("metadata.json unreadable or missing")
    else:
        if not isinstance(meta, dict):
            issues.append("metadata.json must be an object")
        else:
            # Optional checks
            if "created_at" not in meta:
                issues.append("metadata.json missing 'created_at' field")
            if "privacy" in meta and meta.get("privacy") not in ("public", "private", "restricted"):
                issues.append("metadata.json 'privacy' field should be one of: public, private, restricted")

    status = "ok" if len(issues) == 0 else "warn"
    return {"status": status, "issues": issues}


def inspect(subchat_id: str, root: Optional[Path] = None) -> Dict[str, Any]:
    """
    Return an inspection report for the subchat. Non-destructive (read-only).
    Includes: validation, metadata, message stats, sample messages, last activity.
    """
    root = root or SUBCHAT_ROOT
    sc_path = root / subchat_id
    if not sc_path.exists():
        return {"status": "error", "error": f"Subchat '{subchat_id}' not found"}

    validation = validate(subchat_id, root=root)
    meta = _read_json(sc_path / "metadata.json") or {}
    convo = _read_json(sc_path / "conversation.json") or []

    # Stats
    total_msgs = len(convo)
    top_senders: Dict[str, int] = {}
    for m in convo:
        sender = m.get("sender", "unknown")
        top_senders[sender] = top_senders.get(sender, 0) + 1

    sorted_senders = sorted(top_senders.items(), key=lambda x: -x[1])[:10]
    last_activity = None
    if total_msgs:
        try:
            last_activity = convo[-1].get("timestamp")
        except Exception:
            last_activity = None

    # Build sample messages (first, last, random few)
    sample = []
    if total_msgs > 0:
        sample.append(convo[0])
        if total_msgs > 1:
            sample.append(convo[-1])
        if total_msgs > 2:
            # include middle message(s) if present
            mid = convo[total_msgs // 2]
            sample.append(mid)

    report = {
        "status": "ok",
        "subchat_id": subchat_id,
        "validation": validation,
        "metadata": meta,
        "stats": {
            "total_messages": total_msgs,
            "unique_senders": len(top_senders),
            "top_senders": sorted_senders,
            "last_activity": last_activity,
        },
        "samples": sample,
    }
    return report


def summarize(subchat_id: str, max_messages: int = 5, root: Optional[Path] = None) -> str:
    """
    Create a concise textual summary of the subchat.
    This is a heuristic, simple summarizer (no external LLM calls).
    """
    root = root or SUBCHAT_ROOT
    sc_path = root / subchat_id
    convo = _read_json(sc_path / "conversation.json") or []

    if not convo:
        return f"Subchat '{subchat_id}' has no messages."

    total = len(convo)
    participants = list({m.get("sender", "unknown") for m in convo})
    first = convo[0]
    last = convo[-1]

    # Collect short highlights
    highlights = []
    for m in convo[-max_messages:]:
        text = m.get("text", "")
        if text:
            snippet = text.strip().replace("\n", " ")
            if len(snippet) > 200:
                snippet = snippet[:197] + "..."
            highlights.append(f"- [{m.get('sender','?')}] {snippet}")

    summary_lines = [
        f"Subchat ID: {subchat_id}",
        f"Messages: {total}",
        f"Participants: {', '.join(participants)}",
        f"First message at: {first.get('timestamp', 'unknown')}",
        f"Last message at: {last.get('timestamp', 'unknown')}",
        "Recent highlights:",
        *highlights
    ]
    return "\n".join(summary_lines)


def export_report(subchat_id: str, out_path: Path, root: Optional[Path] = None) -> Dict[str, Any]:
    """
    Export the full inspection report as JSON to out_path (overwrites).
    Returns dict with status and path.
    """
    root = root or SUBCHAT_ROOT
    out_path = Path(out_path)
    report = inspect(subchat_id, root=root)
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        return {"status": "ok", "path": str(out_path)}
    except Exception as e:
        logger.exception("Failed to export report: %s", e)
        return {"status": "error", "error": str(e)}


# --- CLI support ---------------------------------------------------------
def _cli_list(args: argparse.Namespace) -> int:
    root = Path(args.root) if args.root else SUBCHAT_ROOT
    scs = list_subchats(root=root)
    if not scs:
        print("No subchats found.")
        return 0
    print("Subchats:")
    for s in scs:
        print(" -", s)
    return 0


def _cli_inspect(args: argparse.Namespace) -> int:
    root = Path(args.root) if args.root else SUBCHAT_ROOT
    report = inspect(args.subchat, root=root)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


def _cli_validate(args: argparse.Namespace) -> int:
    root = Path(args.root) if args.root else SUBCHAT_ROOT
    result = validate(args.subchat, root=root)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def _cli_summarize(args: argparse.Namespace) -> int:
    root = Path(args.root) if args.root else SUBCHAT_ROOT
    text = summarize(args.subchat, max_messages=args.max_messages, root=root)
    print(text)
    return 0


def _cli_export(args: argparse.Namespace) -> int:
    root = Path(args.root) if args.root else SUBCHAT_ROOT
    res = export_report(args.subchat, Path(args.output), root=root)
    print(json.dumps(res, indent=2, ensure_ascii=False))
    return 0


def main():
    parser = argparse.ArgumentParser(prog="subchat_inspector", description="Inspect and report on PRIMUS subchats")
    parser.add_argument("--root", help="Override subchat root directory (for testing)")

    sub = parser.add_subparsers(dest="cmd", required=True)

    sub_list = sub.add_parser("list", help="List subchats")
    sub_list.set_defaults(func=_cli_list)

    sub_inspect = sub.add_parser("inspect", help="Inspect a subchat")
    sub_inspect.add_argument("subchat", help="Subchat id (folder name)")
    sub_inspect.set_defaults(func=_cli_inspect)

    sub_validate = sub.add_parser("validate", help="Validate a subchat")
    sub_validate.add_argument("subchat", help="Subchat id (folder name)")
    sub_validate.set_defaults(func=_cli_validate)

    sub_summarize = sub.add_parser("summarize", help="Summarize a subchat (text)")
    sub_summarize.add_argument("subchat", help="Subchat id (folder name)")
    sub_summarize.add_argument("--max-messages", type=int, default=5)
    sub_summarize.set_defaults(func=_cli_summarize)

    sub_export = sub.add_parser("export", help="Export JSON report for a subchat")
    sub_export.add_argument("subchat", help="Subchat id (folder name)")
    sub_export.add_argument("output", help="Output file path")
    sub_export.set_defaults(func=_cli_export)

    args = parser.parse_args()
    try:
        return args.func(args)
    except Exception as e:
        logger.exception("Error in subchat_inspector: %s", e)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())