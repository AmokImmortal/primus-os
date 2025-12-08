# Security Smoke Tests for Primus OS

This file describes **manual, low-effort checks** to confirm that basic security wiring is behaving as expected.

These are *smoke tests*, not a full audit. They should be safe to run on a dev machine and help you catch obvious regressions quickly.


---

## 1. Bootup Security Snapshot

**Goal:** Confirm the security layer & enforcer wire up cleanly and report status.

### Command

```bash
python core/primus_runtime.py --run-bootup-test
