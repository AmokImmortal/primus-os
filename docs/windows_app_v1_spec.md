# Primus OS – Windows App v1 Specification

## 1. Purpose & Vision

The **Primus OS Windows App v1** is a **thin desktop wrapper** around the existing Primus core:

- Provide a **simple, friendly chat UI** instead of using `primus_cli.py` directly.
- Let the user **choose sessions**, toggle **RAG on/off**, and see **basic status** (model, RAG, security).
- Reuse **existing CLI + PrimusCore** as much as possible (low risk, low complexity).
- Keep it **offline-first, local-only**, matching the current security model (no external network calls by default).

This is **not** a full “OS shell” or system tray daemon yet. It’s a **v1 GUI frontend** to what we’ve already built.

---

## 2. Scope (v1)

### 2.1 In-scope features

1. **Chat UI**
   - Single main window with:
     - Scrollable **chat transcript**.
     - **Input box** for user messages.
     - **Send** button (and Enter key to send).
   - Messages are streamed as plain text (no markdown formatting required in v1).

2. **Session controls**
   - A **session ID** field (text box or dropdown) with:
     - Default: `cli`.
     - Recently used session IDs cached in the app.
   - “New session” button that:
     - Suggests a simple new ID (e.g. timestamp-based or user-entered).
     - Switches the UI to that session.
   - “View History” button that:
     - Shows last N messages for the current session (via `session-history`).

3. **RAG controls**
   - **Checkbox / toggle**: “Use RAG”.
   - **Text field**: “RAG index name” (default: `docs`).
   - These map directly to existing CLI flags:
     - `--rag` (boolean).
     - `--index` (string, default `docs`).

4. **Status + health**
   - Simple **status bar** showing:
     - Model path short name (e.g. derived from `PRIMUS_MODEL_PATH` or runtime info).
     - RAG index status (“docs indexed” / “not indexed yet”).
     - Security mode / Captain’s Log mode if available (read-only indicator).
   - “Run core bootup test” button:
     - Runs `python core/primus_runtime.py --run-bootup-test`.
     - Shows **PASS / FAIL** and a short textual summary.

5. **Logs & docs quick links**
   - Buttons:
     - “Open logs folder” → opens `logs/` in File Explorer.
     - “Open docs folder” → opens `docs/` in File Explorer.

6. **Basic error handling**
   - If Primus CLI or Python subprocess fails:
     - Show a **clear error toast or banner** (e.g. “Model not configured – check PRIMUS_MODEL_PATH.”).
     - Do **not** crash the app.
   - All subprocess stderr/stdout should be logged to an app-local log file as well.

---

## 3. Explicit Non-Goals (v1)

- **No multi-window / multi-chat tab** layout.
- **No streaming token-by-token** output (wait for full reply).
- **No remote network access** from the app itself (matches security gate model).
- **No automatic installation** of Python, models, or Primus. v1 assumes the user already has:
  - Primus OS repo cloned.
  - `venv` created and activated.
  - `PRIMUS_MODEL_PATH` set correctly.
- **No complex Captain’s Log UI** (can be added later).

---

## 4. Environment & Prerequisites

### 4.1 File layout assumptions

The app assumes:

- Primus root: `C:\P.R.I.M.U.S OS\System`
- Within that root:
  - `primus_cli.py`
  - `core/primus_core.py`
  - `core/primus_runtime.py`
  - `core/session_manager.py`
  - `docs/`
  - `logs/`
  - `system/sessions/` (or equivalent session directory managed by `SessionManager`)

### 4.2 Runtime assumptions

- A working **virtualenv** at `C:\P.R.I.M.U.S OS\System\venv`.
- The Windows app **launches Primus through that venv**, e.g.:

  - Option A (preferred for v1):  
    - App spawns a subprocess:  
      `venv\Scripts\python.exe primus_cli.py ...`

  - Option B (future):  
    - App starts a small local HTTP server that wraps PrimusCore; the GUI talks HTTP instead of CLI.

- Environment variable `PRIMUS_MODEL_PATH` is set, or the user configures it in a small settings dialog (which then writes to an `.env` or a config file the CLI respects).

---

## 5. Architecture Overview

### 5.1 High-level design

- **Frontend (Windows app)**:
  - Runs as a native Windows GUI process (implementation choice).
  - Controls:
    - Chat view.
    - Session / RAG inputs.
    - Status bar, buttons.

- **Backend (existing Primus)**:
  - No changes required for v1.
  - All interactions go through **CLI commands**:
    - `python primus_cli.py chat "..." --session S --rag --index docs`
    - `python primus_cli.py session-history --session S --limit N`
    - `python primus_cli.py session-clear --session S`
    - `python primus_cli.py rag-index docs --recursive`
    - `python primus_cli.py rag-search docs "query"`
    - `python core/primus_runtime.py --run-bootup-test`

### 5.2 IPC / integration

For v1, **IPC strategy** is:

- Use `subprocess` to call Primus CLI commands.
- Capture:
  - **stdout** → primary data (model replies, history).
  - **stderr** → diagnostics / errors; logged and partially surfaced in UI.
- No long-lived daemon or socket in v1.

---

## 6. Feature Details

### 6.1 Chat panel

**Inputs:**

- `Message` text box.
- `Session ID` text box (default `cli`).
- `Use RAG` checkbox.
- `RAG index` text box (default `docs`).

**On send:**

- Build CLI command:

  ```text
  venv\Scripts\python.exe primus_cli.py chat "<user_message>" --session <session_id> [--rag] [--index <index_name>]
Show a “sending…” state while subprocess runs.

On success:

Append:

User: <message>

Assistant: <cli_stdout>

If CLI writes extra RAG context / source hints, display them as part of the assistant’s message (no special formatting needed).

On failure:

Show error banner with:

Exit code.

First line or two of stderr.

6.2 Session history viewer
“View History” button or menu:

Runs:

text
Copy code
venv\Scripts\python.exe primus_cli.py session-history --session <session_id> --limit <N>
Displays the output in a simple scrollable window or side panel.

For v1, parsing is optional:

Minimal: treat the CLI output as preformatted text.

Slightly nicer: parse lines like 01) user : ... and show role + content.

“Clear Session” button:

Runs:

text
Copy code
venv\Scripts\python.exe primus_cli.py session-clear --session <session_id>
On success:

Show “Session cleared” toast.

Optionally refresh session history (which should now show “No history found for session 'sX'.”).

6.3 RAG tooling (optional panel)
Buttons:

“Re-index docs” → primus_cli.py rag-index docs --recursive

“Test RAG: ‘smoke test’” → primus_cli.py rag-search docs "smoke test"

Show raw CLI output in a small log window.

If index is missing or empty, show a gentle warning in status bar.

6.4 Status bar content
Minimum fields:

Core status:

A green/red indicator based on last bootup test.

“Core OK” or “Core error – see details.”

Model:

Show:

Short model name (basename of PRIMUS_MODEL_PATH).

Maybe context length if easy to obtain later (not required v1).

RAG:

Simple “RAG ready” if rag-index docs --recursive has run recently (for v1, rely on a config flag or manual indicator).

Security:

Mirror the “Security Gate” status from the bootup test summary when available:

e.g. “Mode: normal, external_network_allowed: False”.

7. UX Flows
7.1 First run (happy path)
User launches the Windows app.

App attempts a bootup test automatically:

Runs python core/primus_runtime.py --run-bootup-test.

Displays a short success/failure message.

App populates:

Session: cli.

RAG: enabled or disabled by default (configurable).

RAG index: docs.

User types “hello” and presses Send.

App shows assistant reply.

User can then:

Change session ID to s1 and send new messages.

Click “View History” to see the conversation.

7.2 Error flows (examples)
Model not configured:

CLI errors with “No model configured (PRIMUS_MODEL_PATH not set…)”.

App shows banner: “Model not configured. Check PRIMUS_MODEL_PATH or Primus installation.”

Provide a “Show details” link to view error logs.

RAG index not built:

rag-search or RAG-enabled chat yields no useful context.

App suggests: “Try ‘Re-index docs’ first.”

8. Logging & Diagnostics
The Windows app should keep its own logs, e.g.:

logs/windows_app.log

Log entries:

Timestamp.

Command executed (sanitized).

Exit code.

Any stderr captured (first N characters).

Optional: “Export logs” button to open log file location.

9. Security & Privacy Considerations
The app must not make outbound network requests by default.

All prompts & histories remain on the local machine, stored wherever SessionManager writes them.

RAG indexes rely only on local docs/ content.

Long-term: consider simple redactions in UI for obviously sensitive strings (out of scope for v1).

10. Testing Checklist (Windows App v1)
10.1 Pre-conditions
Primus repo cloned to C:\P.R.I.M.U.S OS\System.

venv created and activated for development.

PRIMUS_MODEL_PATH set and verified.

python core/primus_runtime.py --run-bootup-test passes (or only fails model check if model not set).

10.2 Basic app tests
Launch & bootup

App starts without crashing.

Bootup test runs or can be triggered.

Status bar updates.

Chat basic

Send “hello” in session cli.

Receive assistant reply.

No unhandled exceptions or app crashes.

Session persistence

Switch to session s1.

Send “remember this line”.

Use “View History” to confirm the line appears.

Use “Clear Session” then confirm history is empty.

RAG integration

Run “Re-index docs”.

Run a RAG-enabled chat question (e.g. “What is the Primus OS codename?”).

Observe that the model references cli_smoke_tests.md / docs context, not hallucinated data.

Error handling

Temporarily misconfigure model path (for testing).

Attempt chat and confirm app shows a friendly error message, not a crash.

11. Future v2 Ideas (Not in v1)
System tray icon with quick prompts (e.g. “Ask Primus…”).

Streaming generation (token-by-token).

Basic markdown rendering for answers.

Dedicated Captain’s Log tab with journaling UI.

Embedded HTTP micro-service for more efficient bidirectional communication.

Cross-platform builds (Linux, macOS) if demand exists.
