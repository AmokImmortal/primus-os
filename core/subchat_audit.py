"""
/core/subchat_audit.py

Sub-Chat Audit system for PRIMUS OS
Responsibilities:
- Record every subchat interaction (agent <-> agent, primus <-> subchat, etc.)
- Persist audit entries locally (one file per subchat/session) in newline-delimited JSON for append-friendly writes
- Query and export audit logs
- Basic integrity checks and pruning
- Thread-safe write operations

Location (example): C:\P.R.I.M.U.S OS\System\core\subchat_audit.py
"""

from __future__ import annotations
import json
import os
from pathlib import Path
from datetime import datetime, timezone, timedelta
import threading
import hashlib
from typing import Optional, Iterable, Dict, Any, List

# Base directory for audit logs (relative to repository root)
ROOT = Path(__file__).resolve().parents[2]  # .../System
AUDIT_DIR = ROOT / "core" / "audit_logs"
AUDIT_DIR.mkdir(parents=True, exist_ok=True)

# Keep an in-memory lock map to protect concurrent writes per session
_LOCKS: Dict[str, threading.Lock] = {}
_LOCKS_LOCK = threading.Lock()


def _get_lock(session_id: str) -> threading.Lock:
    """Return a per-session lock (create if missing)."""
    with _LOCKS_LOCK:
        if session_id not in _LOCKS:
            _LOCKS[session_id] = threading.Lock()
        return _LOCKS[session_id]


def _session_file(session_id: str) -> Path:
    """Return the file path for a session's audit log (newline-delimited JSON)."""
    safe = hashlib.sha1(session_id.encode("utf-8")).hexdigest()
    return AUDIT_DIR / f"session_{safe}.ndjson"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class AuditEntry:
    """Represents a single audit entry."""

    def __init__(
        self,
        session_id: str,
        actor_from: str,
        actor_to: Optional[str],
        direction: str,
        message: str,
        metadata: Optional[Dict[str, Any]] = None,
        timestamp: Optional[str] = None,
    ):
        """
        direction: "outbound" | "inbound" | "system"
        actor_from: agent/primus id sending the message
        actor_to: agent/primus id receiving the message (or None for broadcasts/system)
        """
        self.session_id = session_id
        self.actor_from = actor_from
        self.actor_to = actor_to
        self.direction = direction
        self.message = message
        self.metadata = metadata or {}
        self.timestamp = timestamp or _now_iso()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "timestamp": self.timestamp,
            "actor_from": self.actor_from,
            "actor_to": self.actor_to,
            "direction": self.direction,
            "message": self.message,
            "metadata": self.metadata,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


class SubchatAudit:
    """
    High-level API for recording and querying audit logs.
    - Append is efficient by writing newline-delimited JSON.
    - Reads parse the whole file (ok for moderate log sizes; implement chunking/pagination later).
    """

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.file = _session_file(session_id)

    def record(
        self,
        actor_from: str,
        actor_to: Optional[str],
        direction: str,
        message: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Append an audit entry to the session log. Returns True on success."""
        entry = AuditEntry(
            session_id=self.session_id,
            actor_from=actor_from,
            actor_to=actor_to,
            direction=direction,
            message=message,
            metadata=metadata,
        )
        lock = _get_lock(self.session_id)
        try:
            with lock:
                # Ensure parent directory exists
                self.file.parent.mkdir(parents=True, exist_ok=True)
                # Append newline-delimited JSON
                with open(self.file, "a", encoding="utf-8") as f:
                    f.write(entry.to_json())
                    f.write("\n")
            return True
        except Exception as e:
            # Basic fallback printing; real system should route to logger
            print(f"[subchat_audit] Failed to record audit entry: {e}")
            return False

    def tail(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Return the last `limit` entries for this session. Reads file into memory (ok for small/medium logs).
        """
        if not self.file.exists():
            return []

        try:
            with open(self.file, "r", encoding="utf-8") as f:
                lines = f.readlines()
            lines = [l.strip() for l in lines if l.strip()]
            selected = lines[-limit:]
            return [json.loads(l) for l in selected]
        except Exception as e:
            print(f"[subchat_audit] Failed to tail logs: {e}")
            return []

    def query(
        self,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        actor: Optional[str] = None,
        contains: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Query entries for this session with optional filters.
        - since / until: timezone-aware datetimes used to filter timestamp
        - actor: filter where actor_from == actor or actor_to == actor
        - contains: substring search against message
        - limit: maximum number of results (most recent first)
        """
        results: List[Dict[str, Any]] = []
        if not self.file.exists():
            return results

        try:
            with open(self.file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except Exception:
                        continue

                    ts = None
                    try:
                        ts = datetime.fromisoformat(obj.get("timestamp"))
                    except Exception:
                        pass

                    if since and ts and ts < since:
                        continue
                    if until and ts and ts > until:
                        continue
                    if actor and not (obj.get("actor_from") == actor or obj.get("actor_to") == actor):
                        continue
                    if contains and contains.lower() not in (obj.get("message", "").lower()):
                        continue

                    results.append(obj)

            # return most recent first
            results = list(reversed(results))
            if limit is not None:
                results = results[:limit]
            return results
        except Exception as e:
            print(f"[subchat_audit] Query error: {e}")
            return []

    def export(self, out_path: str, format: str = "ndjson") -> bool:
        """
        Export audit file for session to out_path.
        Supported format: "ndjson" (raw newline-delimited JSON) or "json" (array).
        """
        if not self.file.exists():
            return False

        p = Path(out_path)
        try:
            if format == "ndjson":
                # Copy file
                p.parent.mkdir(parents=True, exist_ok=True)
                with open(self.file, "r", encoding="utf-8") as src, open(p, "w", encoding="utf-8") as dst:
                    dst.write(src.read())
            elif format == "json":
                entries = []
                with open(self.file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                entries.append(json.loads(line))
                            except Exception:
                                pass
                p.parent.mkdir(parents=True, exist_ok=True)
                with open(p, "w", encoding="utf-8") as out:
                    json.dump(entries, out, indent=2, ensure_ascii=False)
            else:
                raise ValueError("Unsupported export format")
            return True
        except Exception as e:
            print(f"[subchat_audit] Export failed: {e}")
            return False

    def prune_older_than(self, days: int) -> bool:
        """Remove entries older than `days` for this session. This rewrites the session file."""
        if not self.file.exists():
            return True
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        tmp_path = self.file.with_suffix(".tmp")
        kept = 0
        try:
            with open(self.file, "r", encoding="utf-8") as src, open(tmp_path, "w", encoding="utf-8") as dst:
                for line in src:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except Exception:
                        continue
                    ts = None
                    try:
                        ts = datetime.fromisoformat(obj.get("timestamp"))
                    except Exception:
                        pass
                    if ts and ts < cutoff:
                        continue
                    dst.write(json.dumps(obj, ensure_ascii=False))
                    dst.write("\n")
                    kept += 1
            tmp_path.replace(self.file)
            return True
        except Exception as e:
            print(f"[subchat_audit] Prune failed: {e}")
            try:
                if tmp_path.exists():
                    tmp_path.unlink()
            except Exception:
                pass
            return False

    def verify_integrity(self) -> Dict[str, Any]:
        """
        Basic integrity verification:
        - checks file readability
        - attempts to parse each line as JSON
        - returns a small report
        """
        report = {"session_id": self.session_id, "file": str(self.file), "exists": self.file.exists(), "entries_total": 0, "corrupt_lines": 0}
        if not self.file.exists():
            return report
        total = 0
        corrupt = 0
        try:
            with open(self.file, "r", encoding="utf-8") as f:
                for i, line in enumerate(f, start=1):
                    line = line.strip()
                    if not line:
                        continue
                    total += 1
                    try:
                        json.loads(line)
                    except Exception:
                        corrupt += 1
            report["entries_total"] = total
            report["corrupt_lines"] = corrupt
            report["status"] = "ok" if corrupt == 0 else "partial_corruption"
            return report
        except Exception as e:
            report["status"] = "unreadable"
            report["error"] = str(e)
            return report


# -------------------------
# Helper utilities (multi-session)
# -------------------------
def list_sessions() -> List[str]:
    """Return list of session ids (hashed filenames mapped back to file names)."""
    sessions = []
    for p in AUDIT_DIR.glob("session_*.ndjson"):
        # we can't reverse SHA easily; return filename (safe id) and path
        sessions.append(p.name)
    return sessions


def export_all(out_dir: Optional[str] = None, format: str = "ndjson") -> bool:
    """
    Export all session audit logs to a directory. By default copies NDJSON files.
    """
    out_base = Path(out_dir) if out_dir else (ROOT / "core" / "audit_export")
    out_base.mkdir(parents=True, exist_ok=True)
    try:
        for p in AUDIT_DIR.glob("session_*.ndjson"):
            dest = out_base / p.name
            with open(p, "r", encoding="utf-8") as src, open(dest, "w", encoding="utf-8") as dst:
                if format == "ndjson":
                    dst.write(src.read())
                elif format == "json":
                    entries = [json.loads(l) for l in src.read().splitlines() if l.strip()]
                    json.dump(entries, dst, indent=2, ensure_ascii=False)
                else:
                    raise ValueError("Unsupported format")
        return True
    except Exception as e:
        print(f"[subchat_audit] export_all failed: {e}")
        return False