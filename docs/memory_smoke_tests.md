# PRIMUS OS – Memory Smoke Tests

Goal: quick manual checks that session-based memory behaves as expected when
using the CLI `chat` command with `--session`.

> NOTE: These tests assume:
> - `primus_cli.py` supports `--session`
> - `PrimusCore.chat(...)` persists history via `SessionManager`

---

## 1. Basic “remember my last line” (single session)

**Commands**

1. `python primus_cli.py chat "Remember this exact phrase: BLUE STAR MEMORY." --session s_mem1`
2. `python primus_cli.py chat "What phrase did I ask you to remember?" --session s_mem1`

**Expected behavior**

- Step 1: Model acknowledges storing / remembering something.
- Step 2: Reply explicitly mentions **“BLUE STAR MEMORY”** (or a close paraphrase)
  and clearly ties it to the earlier turn.

**Failure signs**

- Model answers generically (e.g. “I don’t know” or “You asked me a question”)
  with no reference to the stored phrase.
- Reply looks like a completely unrelated hallucination.

---

## 2. Isolation between sessions

**Commands**

1. `python primus_cli.py chat "Remember this: RED SESSION ONLY." --session s_red`
2. `python primus_cli.py chat "What did I ask you to remember?" --session s_red`
3. `python primus_cli.py chat "What did I ask you to remember?" --session s_blue`

**Expected behavior**

- Step 2: Mentions **“RED SESSION ONLY”**.
- Step 3: Either:
  - Says it doesn’t know / has no prior info for `s_blue`, or
  - Clearly indicates there’s no previous memory for that session.

**Failure signs**

- `s_blue` answer incorrectly mentions **“RED SESSION ONLY”**.
- Both sessions appear to share one unified history.

---

## 3. Longer short conversation (3–4 turns)

**Commands (same session)**

1. `python primus_cli.py chat "Hi, my name is Orion." --session s_conv`
2. `python primus_cli.py chat "I like cyan UI themes." --session s_conv`
3. `python primus_cli.py chat "What is my name and what color themes do I like?" --session s_conv`

**Expected behavior**

- Step 3: Reply should correctly say name = **Orion** and themes = **cyan**,
  and make it clear it’s summarizing earlier turns.

**Failure signs**

- Gets either the name or preference wrong.
- Talks about the right facts but attributes them to “someone” instead of the user.
- Completely ignores history and answers from generic prior knowledge.

---

## 4. Session reset / new session sanity

**Commands**

1. `python primus_cli.py chat "My name is Vega." --session s_reset`
2. `python primus_cli.py chat "What is my name?" --session s_reset`
3. `python primus_cli.py chat "What is my name?" --session s_reset2`

**Expected behavior**

- Step 2: Reply should say **Vega**.
- Step 3: Should NOT confidently say Vega; instead:
  - Admit it doesn’t know yet, OR
  - Ask you to tell it your name.

**Failure signs**

- Both sessions s_reset and s_reset2 claim your name is Vega without any prior
  context in s_reset2.

---

## 5. Memory + RAG (light integration check)

*(Only run once RAG flags are wired through the CLI.)*

**Commands**

1. `python primus_cli.py chat "My callsign is NOVA. Also, what is the Primus OS codename?" --session s_rag_mem --rag --index docs`
2. `python primus_cli.py chat "Without re-reading the docs, remind me: what is my callsign?" --session s_rag_mem`

**Expected behavior**

- Step 1:
  - Answer includes correct Primus OS codename (from `rag_test_primus.txt`).
  - Acknowledges that your callsign is NOVA.
- Step 2:
  - Mentions **NOVA** from session history without needing RAG context.

**Failure signs**

- Step 2: Only talks about the codename and ignores your callsign.
- Step 2: Clearly re-reads docs and confuses “codename” with “callsign”.

---

## 6. Quick regression checklist

When you change anything in:

- `core/primus_core.py` (chat / session / RAG)
- `core/session_manager.py`
- `primus_cli.py` (session flags or chat handling)

Run at least:

1. Test 1 (basic remember).
2. Test 2 (session isolation).
3. Test 3 (3–4 turn conversation).

If any fail, fix before moving on to more complex changes.

## CLI memory tests (sessions via chat + session-history/session-clear)

These checks validate that Primus OS:

- Persists per-session chat history.
- Lets you inspect that history from the CLI.
- Lets you clear history so future chats start “fresh”.

> Assumes:
> - You are in `C:\P.R.I.M.U.S OS\System`
> - Virtualenv is active: `(venv)`
> - Model is configured via `PRIMUS_MODEL_PATH`

### 1. Write memory into a session

**Goal:** Create a small conversation in a named session that should be persisted.

**Commands**

```bash
python primus_cli.py chat "remember this line" --session s1
python primus_cli.py chat "what did I just say?" --session s1
What to look for

The second response ideally acknowledges the previous turn (it may not be perfect, but it should feel like the same conversation).

No crashes or tracebacks.

2. Inspect that session’s history
Goal: Confirm that the “remember this line” conversation is stored.

Command

bash
Copy code
python primus_cli.py session-history --session s1 --limit 10
What to look for

Output shows an ordered list of messages including something like:

user: remember this line

assistant: ...

user: what did I just say?

assistant: ...

If history is missing, the command should clearly say so (not crash).

3. Clear the session and verify
Goal: Remove the stored history and confirm it is actually gone.

Commands

bash
Copy code
python primus_cli.py session-clear --session s1

# Optional verification
python primus_cli.py session-history --session s1 --limit 10
What to look for

session-clear runs without errors.

Follow-up session-history for s1 shows no messages or an explicit “empty” indication.

4. Fresh behavior after clear
Goal: Ensure the next chat on s1 behaves like a new conversation.

Command

bash
Copy code
python primus_cli.py chat "what did I just say?" --session s1
What to look for

The model should not confidently reference the old “remember this line” exchange.

A generic or “I don’t know / you haven’t told me yet” style answer is acceptable.

This confirms that cleared history is not silently being reused.

pgsql
Copy code

### Where to put this

- Place this **after your existing high-level memory overview** in `docs/memory_smoke_tests.md`.
- Concretely: if the file already has sections like “Overview” / “Goals”, put this right after those, before any deeper/advanced memory tests.  
- If you already have numbered sections, just continue the numbering to match the rest of the file.
::contentReference[oaicite:0]{index=0}
