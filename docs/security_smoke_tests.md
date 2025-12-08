# Security Smoke Tests for Primus OS

This file describes **manual, low-effort checks** to confirm that basic security wiring is behaving as expected.

These are *smoke tests*, not a full audit. They should be safe to run on a dev machine and help you catch obvious regressions quickly.


---

## 1. Bootup Security Snapshot

**Goal:** Confirm the security layer & enforcer wire up cleanly and report status.

### Command

```bash
python core/primus_runtime.py --run-bootup-test
Expected Output (high level)
A “Security layer” line:

Usually Security layer : WORKING or DEGRADED with a clear reason.

A “security snapshot” JSON block with at least:

sandbox_active (bool)

password_configured (bool)

pending_approvals (int)

A “security_enforcer” status (may be null in very early/dev setups).

Final line:

Bootup Test : ALL CHECKS PASSED. or a clear FAILED reason.

Red Flags
Tracebacks or uncaught exceptions during the snapshot section.

Bootup Test : ONE OR MORE CHECKS FAILED. without an obvious intentional reason.

Security layer import errors that suddenly appear after recent changes.

2. Security Layer Presence (Import Sanity)
Goal: Confirm that core modules that optionally depend on security do not crash if the security layer is missing or degraded.

Commands
Run these in an environment where the security layer may be disabled or minimal:

bash
Copy code
python -m py_compile core/primus_runtime.py
python core/primus_runtime.py --run-bootup-test
Expected Behavior
Compilation succeeds (no syntax errors).

Bootup test runs to completion, even if:

Some security-related sections are marked as DEGRADED or MISSING.

No hard crashes when security modules are not fully configured.

Red Flags
Import errors that kill the process (e.g., ModuleNotFoundError for security modules).

Unhandled exceptions in security preflight code.

3. Security Gate Status (If Available)
Goal: Verify that the Security Gate (if implemented) reports a sane status and doesn’t crash other systems.

Command
bash
Copy code
python core/primus_runtime.py --run-bootup-test
Expected Output (snippet)
Look for a line like:

text
Copy code
Security Gate      : WORKING (mode=normal, external_network_allowed=False)
or

text
Copy code
Security Gate      : MISSING (not initialized)
Red Flags
Security Gate section crashes the whole bootup test.

Clearly contradictory status, such as:

mode=normal with weird/garbled extra fields.

Sudden change from WORKING → FAILED after unrelated code changes.

4. Basic “No Secrets in Logs” Sanity Check
Goal: Ensure the most obvious sensitive values (passwords / API keys) are not accidentally printed in high-level logs during normal boot.

Steps
Ensure your environment variables / config include some dummy secret-like values:

e.g. PRIMUS_DUMMY_SECRET=super-secret-test-value

Run:

bash
Copy code
python core/primus_runtime.py --run-bootup-test > logs/security_smoke_stdout.txt 2>&1
Search the captured output for:

Any exact secrets you configured.

Obvious “password” fields.

Expected Behavior
No environment variable values or secret strings appear in the top-level stdout/stderr logs.

High-level logs may mention that a password exists (e.g., password_configured: true) but not the raw password.

Red Flags
Exact secret values logged in plaintext.

Stack traces that dump entire config dicts including credentials.

5. CLI Graceful Degradation Without Security
Goal: Confirm that CLI commands still work if the security layer is missing / disabled, and that the user gets clear messaging instead of crashes.

Note: This is a conceptual test; on some setups you might not actually remove modules, just simulate minimal security.

Commands (normal dev environment)
bash
Copy code
python primus_cli.py rag-index docs --recursive
python primus_cli.py rag-search docs "smoke test"
python primus_cli.py chat "hello"
Expected Behavior
Commands succeed or fail purely based on RAG/model/CLI configuration, not because a security module is absent.

If a security-dependent feature is invoked later, errors should be:

Clear, human-readable

Not full, cryptic tracebacks for normal user actions.

Red Flags
Any CLI command fails with a raw security-related import error.

Security-specific tracebacks show up in simple chat or rag-* workflows.

6. Regression Checklist (Before Merging Security-Adjacent Changes)
Before merging changes that touch:

core/primus_runtime.py

core/security_gate.py / security/ layer

any new “enforcer” / approval features

Run:

python -m py_compile core/primus_core.py core/primus_runtime.py primus_cli.py

python core/primus_runtime.py --run-bootup-test

python primus_cli.py chat "hello"

Verify:

No new security warnings beyond what you expect.

No stack traces.

Bootup test still ends with ALL CHECKS PASSED or clearly intentional degradations.

Notes
These tests are deliberately lightweight. They’re meant to be run frequently.

They do not replace:

Code review for auth logic

Threat modeling

Penetration testing or external security assessment

If any security smoke test starts failing after a change, treat it as a blocking issue until you understand why.

makefile
Copy code
::contentReference[oaicite:0]{index=0}






