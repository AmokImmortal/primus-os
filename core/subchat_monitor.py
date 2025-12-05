"""
Subchat Monitor for PRIMUS
Tracks health, heartbeats, activity, timeouts and recovery for subchats.
Persists state to disk so monitor survives restarts.

Location: C:\P.R.I.M.U.S OS\System\core\subchat_monitor.py
"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Callable, Dict, Optional

# Logger setup (safe: won't duplicate handlers)
logger = logging.getLogger("core.subchat_monitor")
if not logger.handlers:
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter("[subchat_monitor] %(asctime)s %(levelname)s: %(message)s"))
    logger.addHandler(ch)
logger.setLevel(logging.INFO)


CORE_DIR = Path(__file__).resolve().parent
STATE_FILE = CORE_DIR / "subchat_monitor_state.json"


@dataclass
class SubchatStatus:
    id: str
    name: Optional[str] = None
    last_heartbeat: float = field(default_factory=lambda: time.time())
    created_at: float = field(default_factory=lambda: time.time())
    state: str = "healthy"  # healthy | degraded | offline | recovering
    metadata: Dict = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)


class SubchatMonitor:
    """
    Monitors registered subchats, tracks heartbeats and triggers callbacks on timeout/recovery.

    Basic usage:
        monitor = SubchatMonitor(timeout_seconds=60, monitor_interval=5)
        monitor.register_subchat("agent_mobile", name="Mobile Detailing")
        monitor.start()
        monitor.heartbeat("agent_mobile")
        ...
        monitor.stop()
    """

    def __init__(
        self,
        timeout_seconds: int = 60,
        monitor_interval: float = 5.0,
        state_path: Optional[Path] = None,
        on_timeout: Optional[Callable[[SubchatStatus], None]] = None,
        on_recover: Optional[Callable[[SubchatStatus], None]] = None,
    ):
        self.timeout_seconds = int(timeout_seconds)
        self.monitor_interval = float(monitor_interval)
        self.state_path = Path(state_path) if state_path else STATE_FILE

        self._lock = threading.RLock()
        self._running = False
        self._thread: Optional[threading.Thread] = None

        self.registry: Dict[str, SubchatStatus] = {}

        # callbacks
        self.on_timeout = on_timeout
        self.on_recover = on_recover

        # attempt to load persistent state
        self._load_state()

    # ------------------------
    # Persistence
    # ------------------------
    def _load_state(self):
        try:
            if self.state_path.exists():
                with open(self.state_path, "r", encoding="utf-8") as f:
                    obj = json.load(f)
                loaded = {}
                for sid, data in obj.items():
                    status = SubchatStatus(
                        id=data.get("id", sid),
                        name=data.get("name"),
                        last_heartbeat=float(data.get("last_heartbeat", time.time())),
                        created_at=float(data.get("created_at", time.time())),
                        state=data.get("state", "healthy"),
                        metadata=data.get("metadata", {}),
                    )
                    loaded[sid] = status
                with self._lock:
                    self.registry = loaded
                logger.info("Loaded subchat monitor state (%d entries)", len(loaded))
        except Exception as e:
            logger.exception("Failed to load state: %s", e)

    def _save_state(self):
        try:
            to_save = {sid: s.to_dict() for sid, s in self.registry.items()}
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.state_path, "w", encoding="utf-8") as f:
                json.dump(to_save, f, indent=2)
            logger.debug("Saved state to %s", self.state_path)
        except Exception as e:
            logger.exception("Failed to save state: %s", e)

    # ------------------------
    # Registry management
    # ------------------------
    def register_subchat(self, sid: str, name: Optional[str] = None, metadata: Optional[Dict] = None) -> SubchatStatus:
        with self._lock:
            if sid in self.registry:
                status = self.registry[sid]
                if name:
                    status.name = name
                if metadata:
                    status.metadata.update(metadata)
                logger.debug("Updated registration for subchat '%s'", sid)
            else:
                status = SubchatStatus(id=sid, name=name, metadata=metadata or {})
                self.registry[sid] = status
                logger.info("Registered subchat '%s' (name=%s)", sid, name)
            self._save_state()
            return status

    def unregister_subchat(self, sid: str) -> bool:
        with self._lock:
            if sid in self.registry:
                del self.registry[sid]
                logger.info("Unregistered subchat '%s'", sid)
                self._save_state()
                return True
            return False

    def heartbeat(self, sid: str) -> SubchatStatus:
        """Record a heartbeat (should be called periodically by subchat)."""
        with self._lock:
            if sid not in self.registry:
                self.register_subchat(sid)
            status = self.registry[sid]
            prev_state = status.state
            status.last_heartbeat = time.time()
            if prev_state in ("degraded", "offline", "recovering"):
                status.state = "healthy"
                logger.info("Subchat '%s' recovered -> healthy", sid)
                if self.on_recover:
                    try:
                        self.on_recover(status)
                    except Exception:
                        logger.exception("on_recover callback failed for %s", sid)
            self._save_state()
            logger.debug("Heartbeat received for '%s' (prev_state=%s)", sid, prev_state)
            return status

    def get_status(self, sid: str) -> Optional[SubchatStatus]:
        with self._lock:
            return self.registry.get(sid)

    def get_all_statuses(self) -> Dict[str, SubchatStatus]:
        with self._lock:
            return dict(self.registry)

    # ------------------------
    # Monitoring loop
    # ------------------------
    def _check_timeouts(self):
        now = time.time()
        timed_out = []
        with self._lock:
            for sid, status in self.registry.items():
                age = now - status.last_heartbeat
                if status.state == "healthy" and age > self.timeout_seconds:
                    status.state = "degraded"
                    timed_out.append(status)
                    logger.warning("Subchat '%s' degraded (last_heartbeat=%.1fs ago)", sid, age)
                elif status.state == "degraded" and age > (self.timeout_seconds * 3):
                    status.state = "offline"
                    timed_out.append(status)
                    logger.error("Subchat '%s' marked offline (last_heartbeat=%.1fs ago)", sid, age)
            if timed_out:
                self._save_state()

        # callbacks outside lock
        for s in timed_out:
            if self.on_timeout:
                try:
                    self.on_timeout(s)
                except Exception:
                    logger.exception("on_timeout callback failed for %s", s.id)

    def _monitor_loop(self):
        logger.info("SubchatMonitor started (interval=%ss, timeout=%ss)", self.monitor_interval, self.timeout_seconds)
        try:
            while self._running:
                try:
                    self._check_timeouts()
                except Exception:
                    logger.exception("Error during timeout check")
                time.sleep(self.monitor_interval)
        finally:
            logger.info("SubchatMonitor stopped")

    def start(self):
        with self._lock:
            if self._running:
                logger.debug("Monitor already running")
                return
            self._running = True
            self._thread = threading.Thread(target=self._monitor_loop, daemon=True, name="subchat-monitor")
            self._thread.start()

    def stop(self, join: bool = True):
        with self._lock:
            self._running = False
        if join and self._thread:
            self._thread.join(timeout=5.0)
            self._thread = None

    # ------------------------
    # Utilities
    # ------------------------
    def force_mark_offline(self, sid: str) -> bool:
        with self._lock:
            s = self.registry.get(sid)
            if s:
                s.state = "offline"
                self._save_state()
                logger.info("Subchat '%s' forced offline", sid)
                return True
            return False

    def force_mark_healthy(self, sid: str) -> bool:
        with self._lock:
            s = self.registry.get(sid)
            if s:
                s.state = "healthy"
                s.last_heartbeat = time.time()
                self._save_state()
                logger.info("Subchat '%s' forced healthy", sid)
                return True
            return False

    def clear_registry(self):
        with self._lock:
            self.registry = {}
            try:
                if self.state_path.exists():
                    self.state_path.unlink()
                logger.info("Cleared subchat registry and removed state file")
            except Exception:
                logger.exception("Failed to remove state file")

    # context manager
    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.stop()


# ------------------------
# Default handlers and singleton helper
# ------------------------
def default_timeout_handler(status: SubchatStatus):
    logger.warning("Default timeout handler triggered for subchat '%s' (state=%s)", status.id, status.state)


def default_recover_handler(status: SubchatStatus):
    logger.info("Default recover handler: subchat '%s' healthy again", status.id)


_monitor_singleton: Optional[SubchatMonitor] = None


def get_monitor_singleton(timeout_seconds: int = 60, monitor_interval: float = 5.0) -> SubchatMonitor:
    global _monitor_singleton
    if _monitor_singleton is None:
        _monitor_singleton = SubchatMonitor(
            timeout_seconds=timeout_seconds,
            monitor_interval=monitor_interval,
            on_timeout=default_timeout_handler,
            on_recover=default_recover_handler,
        )
    return _monitor_singleton


if __name__ == "__main__":
    # Simple demo when run directly
    m = get_monitor_singleton(timeout_seconds=10, monitor_interval=2)
    m.start()
    m.register_subchat("demo", name="Demo Subchat")
    for i in range(3):
        time.sleep(3)
        m.heartbeat("demo")
        logger.info("Demo heartbeat sent")
    logger.info("Sleeping to force degradation...")
    time.sleep(15)
    m.stop()
    logger.info("Demo finished.")