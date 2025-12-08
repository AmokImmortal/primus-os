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
