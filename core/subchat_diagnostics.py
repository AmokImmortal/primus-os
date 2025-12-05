import traceback
import time
from typing import Dict, Any, List


class SubchatDiagnostics:
    """
    Provides deep diagnostics, anomaly detection, and runtime health checks
    for ALL Subchat modules.
    """

    def __init__(self):
        self.last_health_report: Dict[str, Any] = {}
        self.anomaly_log: List[Dict[str, Any]] = []

    # -----------------------------------------------------------
    # CORE HEALTH CHECKS
    # -----------------------------------------------------------

    def check_health(self, components: Dict[str, Any]) -> Dict[str, Any]:
        """
        Runs lightweight health checks on all provided components.
        Expects components = {"name": object, ...}
        """
        report = {"timestamp": time.time(), "components": {}}

        for name, obj in components.items():
            status = "unknown"

            try:
                if hasattr(obj, "is_alive"):
                    status = "alive" if obj.is_alive() else "dead"
                else:
                    # Basic sanity check: object exists and has attributes
                    status = "ok" if obj is not None else "failed"

            except Exception as e:
                status = "error"
                self._record_anomaly(name, str(e))

            report["components"][name] = status

        self.last_health_report = report
        return report

    # -----------------------------------------------------------
    # DEEP DIAGNOSTICS
    # -----------------------------------------------------------

    def deep_diagnostics(self, components: Dict[str, Any]) -> Dict[str, Any]:
        """
        Perform deeper checks — methods, attributes, responsiveness.
        """
        diagnostics = {"timestamp": time.time(), "details": {}}

        for name, obj in components.items():
            details = {"exists": obj is not None}

            try:
                methods = [m for m in dir(obj) if not m.startswith("_")]
                details["method_count"] = len(methods)
                details["methods"] = methods[:25]  # Avoid huge output

                # Optional "ping" method
                if hasattr(obj, "ping"):
                    result = obj.ping()
                    details["ping"] = "ok" if result else "failed"

            except Exception as e:
                details["error"] = str(e)
                self._record_anomaly(name, str(e))

            diagnostics["details"][name] = details

        return diagnostics

    # -----------------------------------------------------------
    # ANOMALY DETECTION
    # -----------------------------------------------------------

    def detect_anomalies(self, health_report: Dict[str, Any]) -> List[str]:
        """
        Analyze the health report for warnings or anomalies.
        """
        anomalies = []

        for name, status in health_report.get("components", {}).items():
            if status not in ("ok", "alive"):
                msg = f"Anomaly detected in '{name}': {status}"
                anomalies.append(msg)
                self._record_anomaly(name, msg)

        return anomalies

    # -----------------------------------------------------------
    # INTERNAL HELPERS
    # -----------------------------------------------------------

    def _record_anomaly(self, component: str, message: str):
        """
        Logs anomalies internally.
        """
        self.anomaly_log.append({
            "timestamp": time.time(),
            "component": component,
            "message": message,
            "stack": traceback.format_exc()
        })

    def get_anomaly_log(self) -> List[Dict[str, Any]]:
        return self.anomaly_log

    def clear_anomaly_log(self):
        self.anomaly_log = []

    # -----------------------------------------------------------
    # UTILITY METHODS
    # -----------------------------------------------------------

    def summarize(self) -> Dict[str, Any]:
        """
        Returns a summary of diagnostics health.
        """
        return {
            "last_health_report": self.last_health_report,
            "total_anomalies": len(self.anomaly_log),
        }