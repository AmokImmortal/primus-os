# PRIMUS OS – CLI Smoke Tests

Quick checks to confirm that the core pieces of PRIMUS OS are wired up correctly.

> These tests assume:
> - You are in the `C:\P.R.I.M.U.S OS\System` directory.
> - Your virtualenv is active (`(venv)`).
> - `PRIMUS_MODEL_PATH` is set to your GGUF model.

---

## 1. Bootup & core health

**Command**

```bash
python core/primus_runtime.py --run-bootup-test
Expected

No Python tracebacks.

Final lines include:

Core self-test : COMPLETED (see logs for details)

Bootup Test : ALL CHECKS PASSED.

If this fails, fix core issues before running anything else.

2. RAG indexing
2.1 Index the docs folder
Command

bash
Copy code
python primus_cli.py rag-index docs --recursive
Expected

No tracebacks.

Logs show RAG initialization.

Final line similar to:

text
Copy code
[OK] Indexed 'C:\P.R.I.M.U.S OS\System\docs' as index 'docs'
If this fails, check that docs/ exists and that rag/indexer.py is importable.

3. RAG retrieval (hash-mock sanity checks)
Note: the current embedder is hash-based (“hash-mock”) and not truly semantic.
These tests only verify that the pipeline returns scored documents, not that it always picks the “best” one.

3.1 Primus codename
Command

bash
Copy code
python primus_cli.py rag-search docs "What is the Primus OS codename?"
Expected

No tracebacks.

1–3 lines of output like:

text
Copy code
[0.xxxx] C:\P.R.I.M.U.S OS\System\docs\some_file.txt
At least one of the results should be a real file under docs\.

3.2 Captain’s Log purpose
Command

bash
Copy code
python primus_cli.py rag-search docs "What is Captain's Log for?"
Expected

Same as above: no errors, 1–3 scored paths.

One of the results is often rag_test_captains_log.txt (but ranking is not guaranteed with hash-mock).

3.3 Decoy note query
Command

bash
Copy code
python primus_cli.py rag-search docs "What kind of facts are in the decoy note?"
Expected

No tracebacks.

Top result is usually rag_test_decoy.txt.

Confirms the pipeline can retrieve that file when the query clearly overlaps its content.

4. Basic chat (CLI)
4.1 Single-turn chat
Command

bash
Copy code
python primus_cli.py chat "hello"
Expected

No tracebacks.

A short assistant reply (1–3 sentences).

Console logs show:

PrimusRuntime initialized.

Calls into the model backend (ModelManager.generate).

5. Core session-aware chat (optional dev checks)
These use PrimusCore directly and are mainly for development/debugging.

5.1 Non-RAG session
Command

bash
Copy code
python -c "from core.primus_core import PrimusCore; from pathlib import Path; core = PrimusCore(system_root=Path('.').resolve()); core.initialize(); print(core.chat('Hello, who are you?', session_id='test_session', use_rag=False))"
Expected

No tracebacks.

Reasonable answer introducing Primus / the assistant.

5.2 RAG session
Command

bash
Copy code
python -c "from core.primus_core import PrimusCore; from pathlib import Path; core = PrimusCore(system_root=Path('.').resolve()); core.initialize(); print(core.chat('What do the docs talk about?', session_id='rag_sess', use_rag=True, rag_index='docs'))"
Expected

No tracebacks.

Answer may reference themes from files in docs/ (subject to model behavior and hash-mock embeddings).

6. Negative check – unknown index
Command

bash
Copy code
python primus_cli.py rag-search unknown_index "test query"
Expected

No Python traceback.

CLI either:

Prints a warning about a missing/empty index, or

Prints no results.

In all cases, the program exits cleanly.

If all sections above pass without tracebacks, the CLI + core + RAG pipeline are considered “smoke-test green”.

makefile
Copy code
::contentReference[oaicite:0]{index=0}
