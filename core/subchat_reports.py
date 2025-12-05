"""
subchat_reports.py
Generates summary reports for subchat activity, audit trails, rule violations,
performance metrics, and lifecycle statistics.

This module DOES NOT store data.
It only reads from:
- subchat_audit.py
- subchat_monitor.py
- subchat_diagnostics.py
- subchat_state.py

All reporting is read-only and cannot modify any system data.
"""

from typing import Dict, Any, List


class SubchatReports:
    def __init__(self, audit_ref, monitor_ref, diagnostics_ref, state_ref):
        """
        audit_ref: instance of SubchatAudit
        monitor_ref: instance of SubchatMonitor
        diagnostics_ref: instance of SubchatDiagnostics
        state_ref: instance of SubchatState
        """
        self.audit = audit_ref
        self.monitor = monitor_ref
        self.diagnostics = diagnostics_ref
        self.state = state_ref

    # ------------------------------------------------------------
    # High-level Report Builders
    # ------------------------------------------------------------

    def build_overview_report(self) -> Dict[str, Any]:
        """Generate a full system summary."""
        return {
            "active_subchats": self.monitor.list_active_subchats(),
            "recent_audit_events": self.audit.get_recent_events(limit=15),
            "system_health": self.diagnostics.get_system_health(),
            "lifecycle_counts": self.state.get_lifecycle_statistics()
        }

    def build_audit_report(self, subchat_id: str) -> Dict[str, Any]:
        """Generate an audit-focused report for a specific subchat."""
        return {
            "subchat_id": subchat_id,
            "audit_history": self.audit.get_history(subchat_id),
            "violation_count": self.audit.count_violations(subchat_id),
            "last_event": self.audit.get_last_event(subchat_id)
        }

    def build_health_report(self, subchat_id: str) -> Dict[str, Any]:
        """Generate a diagnostics-focused report."""
        return {
            "subchat_id": subchat_id,
            "status": self.diagnostics.get_subchat_status(subchat_id),
            "issues": self.diagnostics.list_subchat_issues(subchat_id),
            "performance_metrics": self.monitor.get_subchat_metrics(subchat_id)
        }

    def build_activity_report(self, subchat_id: str) -> Dict[str, Any]:
        """Generate an activity-focused report."""
        return {
            "subchat_id": subchat_id,
            "messages_sent": self.monitor.count_messages(subchat_id),
            "runtime_seconds": self.state.get_runtime(subchat_id),
            "transitions": self.state.get_state_transitions(subchat_id)
        }

    # ------------------------------------------------------------
    # Batch Reporting
    # ------------------------------------------------------------

    def build_all_subchats_overview(self) -> List[Dict[str, Any]]:
        """One overview entry per subchat."""
        IDs = self.monitor.list_all_subchats()
        return [self.build_overview_report_for_id(_id) for _id in IDs]

    def build_overview_report_for_id(self, subchat_id: str) -> Dict[str, Any]:
        return {
            "subchat_id": subchat_id,
            "status": self.diagnostics.get_subchat_status(subchat_id),
            "messages": self.monitor.count_messages(subchat_id),
            "violations": self.audit.count_violations(subchat_id),
            "runtime": self.state.get_runtime(subchat_id)
        }

    # ------------------------------------------------------------
    # Structured Outputs
    # ------------------------------------------------------------

    def export_report(self, report: Dict[str, Any]) -> str:
        """
        Convert a report to a nicely formatted string
        (used for display in terminal/UI panels).
        """
        lines = []
        for key, value in report.items():
            lines.append(f"{key}: {value}")
        return "\n".join(lines)