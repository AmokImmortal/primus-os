# CLI Smoke Tests for Primus OS

This file describes quick, manual checks to verify that the **CLI + runtime + RAG** wiring is still healthy.

These are **smoke tests**, not exhaustive tests. Run them after significant changes to:

- `primus_cli.py`
- `core/primus_runtime.py`
- `core/primus_core.py`
- RAG-related code (`rag/`, `core/rag_manager.py`, etc.)

---

## 0. Environment sanity

From the project root (where `primus_cli.py` lives):

```bash
python -m py_compile core/primus_core.py core/primus_runtime.py primus_cli.py
python core/primus_runtime.py --run-bootup-test
Expected:

No SyntaxError or ImportError.

Bootup test ends with:

Core self-test : COMPLETED (see logs for details)

Bootup Test : ALL CHECKS PASSED.

1. RAG indexing + search (docs index)
Run:

bash
Copy code
python primus_cli.py rag-index docs --recursive
Expected:

Log lines showing PrimusCore initialize and a final line like:

text
Copy code
[OK] Indexed 'C:\P.R.I.M.U.S OS\System\docs' as index 'docs'
Then:

bash
Copy code
python primus_cli.py rag-search docs "smoke test"
Expected:

No traceback.

A few scored lines like:

text
Copy code
[0.1234] C:\P.R.I.M.U.S OS\System\docs\some_file.txt
You don’t care about the exact scores, only that results are returned and the command succeeds.

2. Basic chat via CLI (no session flags)
Run:

bash
Copy code
python primus_cli.py chat "hello"
Expected:

No traceback.

A natural-language reply from the model.

Logging shows PrimusRuntime and PrimusCore initializing once, then a single chat completion.

This is the baseline “single-turn chat still works” check.

3. Session-aware chat (memory check)
Goal: ensure the session ID is respected and stored via SessionManager.

Run:

bash
Copy code
python primus_cli.py chat "remember this line" --session s1
python primus_cli.py chat "what did I just say?" --session s1
Expected:

No traceback on either command.

The second answer should show awareness of the first line (for example, it might paraphrase or explicitly mention “remember this line”).

If you change the session ID, history should not bleed over:

bash
Copy code
python primus_cli.py chat "who are you?" --session s2
Answer should not depend on what was said in s1.

---

## 5. Session inspection & clearing

These tests confirm that:

- Per-session history is actually stored.
- You can inspect that history from the CLI.
- You can clear a session so the next chat starts “fresh”.

### 5.1. Basic session chat

**Goal:** Create a small conversation in a named session.

**Commands**

```bash
python primus_cli.py chat "remember this line" --session s1
python primus_cli.py chat "what did I just say?" --session s1
What to look for

The second call should ideally reference or at least acknowledge the earlier message.

Exact wording will vary by model, but it should feel like the two calls are part of the same conversation, not totally independent.

5.2. Inspect session history
Goal: Verify that the conversation for a session is persisted and inspectable.

Command

bash
Copy code
python primus_cli.py session-history --session s1 --limit 10
What to look for

Output should show an ordered list of messages with roles, e.g.:

user: remember this line

assistant: ...

user: what did I just say?

assistant: ...

If there is no history, the command should print something explicit (e.g. “no messages”), not crash.

5.3. Clear a session
Goal: Confirm that clearing a session removes its history and that future chats no longer see old context.

Commands

bash
Copy code
python primus_cli.py session-clear --session s1

# Optional: verify cleared
python primus_cli.py session-history --session s1 --limit 10
What to look for

session-clear should complete without errors.

A follow-up session-history for s1 should show no messages (or a clear “empty” indication).

5.4. Fresh chat after clear
Goal: Ensure that, after clearing a session, a new chat behaves like a brand-new conversation.

Command

bash
Copy code
python primus_cli.py chat "what did I just say?" --session s1
What to look for

The response should not confidently reference the earlier “remember this line” exchange.

It’s okay if the model says it doesn’t know or gives a generic answer — the key is that old session history is not being reused.

markdown
Copy code

**Where to put it?**

- Stick this after your existing sections for:
  - bootup test
  - basic `rag-index` / `rag-search`
  - basic `chat` / RAG chat
- Or, if you already have numbered sections, just continue the numbering (e.g., if you currently end at `## 3. Chat`, this becomes `## 4. Session inspection & clearing`). The exact position doesn’t affect functionality, just readability.
::contentReference[oaicite:0]{index=0}

4. RAG-aware chat (docs index)
Goal: check that CLI flags --rag and --index are correctly passed through and that the model sees doc content.

First, ensure the docs index exists:

bash
Copy code
python primus_cli.py rag-index docs --recursive
Then run:

bash
Copy code
python primus_cli.py chat "What is the Primus OS codename?" --session s_rag --rag --index docs
Expected:

No traceback.

The answer should reference information that could plausibly come from the docs (especially rag_test_primus.txt), even though the current hash-based embedder is not semantically accurate.

At minimum, logs should show something like:

RAG retrieve request: index='docs' ...

And the model response should look like it saw some context.

You can also ask about Captain’s Log:

bash
Copy code
python primus_cli.py chat "What is Captain's Log for?" --session s_rag --rag --index docs
Expected:

No errors.

The answer should mention Captain’s Log as some kind of logging / audit / special mode (even if not perfectly phrased).

5. Captain’s Log CLI still behaves
(If implemented)

Simple check that the cl command still works and wasn’t broken by changes to chat:

bash
Copy code
python primus_cli.py cl write "test entry from smoke test"
python primus_cli.py cl read
Expected (roughly):

No traceback.

cl write succeeds silently or with a short confirmation.

cl read prints out stored entries, including the smoke test line if your CL backend is wired up.

If Captain’s Log isn’t fully implemented yet, it’s acceptable for these to say something like:

text
Copy code
Captain's Log API is not available on PrimusCore.
as long as the message is clean and there is no traceback.

6. Quick failure triage
If any of the above steps:

Raise an exception / traceback

Hang indefinitely

Or obviously ignore flags (e.g., --session clearly does nothing)

then:

Check recent changes to primus_cli.py, core/primus_runtime.py, and core/primus_core.py.

Re-run:

bash
Copy code
python -m py_compile core/primus_core.py core/primus_runtime.py primus_cli.py
python core/primus_runtime.py --run-bootup-test
Fix the issues before making further feature changes.

pgsql
Copy code

That should give you a solid Codex prompt and an up-to-date smoke-test doc aligned with the new session/RAG flags.
::contentReference[oaicite:0]{index=0}
