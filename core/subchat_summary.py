# /core/subchat_summary.py

"""
Subchat Summary Generator
-------------------------

Produces high-level summaries for:
- Subchat health
- Subchat state
- Recent events
- Policy status
- Security posture
- Diagnostics results

This module acts as the final synthesis layer for the entire Subchat Framework.
"""

from datetime import datetime


class SubchatSummary:
    def __init__(self, state_mgr, events_mgr, diagnostics_mgr, reports_mgr, monitor_mgr):
        self.state_mgr = state_mgr
        self.events_mgr = events_mgr
        self.diagnostics_mgr = diagnostics_mgr
        self.reports_mgr = reports_mgr
        self.monitor_mgr = monitor_mgr

    def generate_summary(self, subchat_id: str) -> dict:
        """
        Returns a complete structured summary for a given subchat.
        """

        state = self.state_mgr.get_state(subchat_id)
        recent_events = self.events_mgr.get_event_log(subchat_id)
        diagnostics = self.diagnostics_mgr.run_diagnostics(subchat_id)
        reports = self.reports_mgr.get_report(subchat_id)
        monitor = self.monitor_mgr.get_status(subchat_id)

        return {
            "subchat_id": subchat_id,
            "timestamp": datetime.utcnow().isoformat(),

            "state": state,
            "recent_events": recent_events,
            "diagnostics": diagnostics,
            "reports": reports,
            "monitor_status": monitor,

            "overall_status": self._derive_overall_status(
                state, diagnostics, monitor
            )
        }

    def _derive_overall_status(self, state, diagnostics, monitor) -> str:
        """
        Simple heuristic for now — upgrade later.
        """

        if diagnostics.get("critical_errors"):
            return "CRITICAL"

        if monitor.get("flags"):
            return "WARNING"

        if state.get("locked"):
            return "LOCKED"

        return "OK"