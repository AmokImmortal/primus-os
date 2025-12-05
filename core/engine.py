# core/engine.py
"""
PRIMUS OS - Core Inference Engine
--------------------------------
Provides a thin, safe adapter between higher-level PRIMUS code (agents, dispatcher,
kernel, UI) and the underlying local model execution provided by core.model_manager.

Features:
- Engine class with methods:
    - generate(prompt, max_tokens=150, temperature=0.7, **kwargs)
    - embed(texts)
    - switch_model(path_or_name)
    - get_status()
- CLI test mode (--test-engine) to verify a model can be loaded and produce output.
- Basic enforcement of internet gating and safety hooks (pluggable).
- Robustness: if optional modules (memory, persona, safety) are missing, engine
  falls back to safe no-op implementations and prints helpful messages.

Usage (from the System root):
    python core/engine.py --test-engine
    python -c "from core.engine import Engine; e=Engine(); print(e.generate('Hello'))"

Note: This file expects there to be a `core/model_manager.py` implementing a ModelManager
class or compatible API. The engine will attempt to import it dynamically and provide
clear errors if the expected interface is missing.
"""

import argparse
import json
import os
import time
from pathlib import Path
import importlib
from typing import Any, Dict, List, Optional

SYSTEM_ROOT = Path(__file__).resolve().parents[1]  # .../System/core -> parents[1] -> System
CONFIGS_DIR = SYSTEM_ROOT / "configs"
LOGS_DIR = SYSTEM_ROOT / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)
ENGINE_LOG = LOGS_DIR / "engine.log"

# ---------- Helpers ----------
def _safe_print(*args, **kwargs):
    print(*args, **kwargs)
    try:
        with open(ENGINE_LOG, "a", encoding="utf-8") as f:
            f.write(" ".join(str(a) for a in args) + "\n")
    except Exception:
        pass


def _load_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


# ---------- Optional plug-ins (memory, persona, safety) ----------
# We try to import these modules; if missing we provide safe no-op implementations
def _import_optional(module_path: str, attr_name: str = None):
    try:
        mod = importlib.import_module(module_path)
        return getattr(mod, attr_name) if attr_name else mod
    except Exception:
        return None


# Memory manager stub / loader
MemoryManagerClass = _import_optional("core.memory", "MemoryManager")
if MemoryManagerClass is None:
    class _MemoryStub:
        def __init__(self, *a, **k):
            _safe_print("[engine] core.memory not found — memory features disabled.")
        def load(self, *a, **k): return {}
        def save(self, *a, **k): return False
        def query(self, *a, **k): return []
    MemoryManagerClass = _MemoryStub

# Persona manager stub / loader
PersonaManagerClass = _import_optional("core.persona", "PersonaManager")
if PersonaManagerClass is None:
    class _PersonaStub:
        def __init__(self, *a, **k):
            _safe_print("[engine] core.persona not found — persona features disabled.")
        def apply(self, prompt: str, persona_name: Optional[str] = None) -> str:
            return prompt
    PersonaManagerClass = _PersonaStub

# Safety / redaction stub
SafetyManagerClass = _import_optional("core.safety", "SafetyManager")
if SafetyManagerClass is None:
    class _SafetyStub:
        def __init__(self, *a, **k):
            _safe_print("[engine] core.safety not found — basic safety checks disabled.")
        def check_send_to_internet(self, payload: Dict[str, Any]) -> bool:
            # return True to allow, False to block (default conservative: block)
            return False
        def sanitize_prompt(self, prompt: str) -> str:
            return prompt
    SafetyManagerClass = _SafetyStub

# Model manager loader (REQUIRED)
ModelManagerClass = None
try:
    ModelManagerClass = _import_optional("core.model_manager", "ModelManager")
    if ModelManagerClass is None:
        # attempt direct module import fallback (when running file-by-file)
        mm_mod = importlib.import_module("core.model_manager")
        ModelManagerClass = getattr(mm_mod, "ModelManager", None)
except Exception:
    # Last resort: try top-level module `model_manager` (if user placed it differently)
    try:
        mm_mod = importlib.import_module("model_manager")
        ModelManagerClass = getattr(mm_mod, "ModelManager", None)
    except Exception:
        ModelManagerClass = None

if ModelManagerClass is None:
    _safe_print("[engine] ERROR: core.model_manager.ModelManager not found. Engine will not operate properly.")


# ---------- Engine ----------
class Engine:
    def __init__(self, model_path: Optional[str] = None, verbose: bool = True):
        self.system_root = SYSTEM_ROOT
        self.verbose = verbose

        # Load configs
        self._paths_config = _load_json(CONFIGS_DIR / "system_paths.json") or {}
        self._model_config = _load_json(CONFIGS_DIR / "model_config.json") or {}
        self._permissions = _load_json(CONFIGS_DIR / "permissions.json") or {}

        # Internet gating (default False unless permissions.json explicitly true)
        self.internet_allowed = bool(self._permissions.get("internet_allowed", False))

        # Instantiate optional managers
        self.memory = MemoryManagerClass() if MemoryManagerClass else None
        self.persona = PersonaManagerClass() if PersonaManagerClass else None
        self.safety = SafetyManagerClass() if SafetyManagerClass else None

        # Model manager (required)
        if ModelManagerClass is None:
            raise RuntimeError("ModelManager not available. Please ensure core/model_manager.py exists and defines ModelManager.")
        self.model_manager = ModelManagerClass(system_root=str(self.system_root))

        # load default model if provided via args/config
        self.model_info = None
        default_model = model_path or self._model_config.get("default_model") or os.environ.get("PRIMUS_DEFAULT_MODEL")
        if default_model:
            try:
                self.model_info = self.model_manager.load_model(default_model)
                _safe_print(f"[engine] Loaded default model: {default_model}")
            except Exception as e:
                _safe_print(f"[engine] Failed to load default model '{default_model}': {e}")

    # ---------- Status / utility ----------
    def get_status(self) -> Dict[str, Any]:
        mm_info = {}
        try:
            mm_info = getattr(self.model_manager, "get_loaded_model_info", lambda: {})()
        except Exception:
            mm_info = {}
        return {
            "system_root": str(self.system_root),
            "internet_allowed": self.internet_allowed,
            "model_manager_info": mm_info
        }

    # ---------- Model management ----------
    def switch_model(self, model_path_or_name: str) -> Dict[str, Any]:
        """
        Load/switch to another model. Returns result dict from model_manager.
        This call does NOT auto-apply changes to system files; it simply instructs
        the model manager to load a different model for inference.
        """
        _safe_print(f"[engine] Switching model -> {model_path_or_name}")
        if not ModelManagerClass:
            return {"status": "error", "error": "ModelManager not available"}
        try:
            res = self.model_manager.load_model(model_path_or_name)
            self.model_info = res
            return {"status": "ok", "model_info": res}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    # ---------- Embedding ----------
    def embed(self, texts: List[str]) -> List[List[float]]:
        """
        Create embeddings for a list of texts. Delegates to model_manager if supported,
        otherwise raises an informative error.
        """
        if not hasattr(self.model_manager, "embed"):
            raise RuntimeError("Current model manager does not support embeddings (no embed()).")
        return self.model_manager.embed(texts)

    # ---------- Generation ----------
    def generate(self,
                 prompt: str,
                 max_tokens: int = 150,
                 temperature: float = 0.7,
                 top_p: float = 0.95,
                 persona: Optional[str] = None,
                 use_rag: bool = False,
                 rag_retriever: Optional[Any] = None,
                 **kwargs) -> Dict[str, Any]:
        """
        Main generation entrypoint used by agents / UI.
        - Applies persona (if available)
        - Sanitizes prompt via safety manager
        - Optionally performs RAG retrieval and prepends retrieved context
        - Calls the model manager's generate method and returns structured dict
        """
        start = time.time()
        # 1) persona
        try:
            if self.persona:
                prompt = self.persona.apply(prompt, persona)
        except Exception as e:
            _safe_print(f"[engine] Persona apply error (continuing): {e}")

        # 2) safety sanitize
        try:
            prompt = self.safety.sanitize_prompt(prompt) if self.safety else prompt
        except Exception as e:
            _safe_print(f"[engine] Safety sanitize error (continuing): {e}")

        # 3) RAG retrieval (optional)
        rag_context = ""
        if use_rag and rag_retriever is not None:
            try:
                hits = rag_retriever.query(prompt)  # expecting list of text
                if hits:
                    rag_context = "\n\n".join(hits)
                    prompt = f"[RAG CONTEXT]\n{rag_context}\n\n[USER PROMPT]\n{prompt}"
            except Exception as e:
                _safe_print(f"[engine] RAG retrieval error (continuing without RAG): {e}")

        # 4) Pre-send internet-safety check (if model_manager would call external resources)
        if not self.internet_allowed and kwargs.get("allow_internet", False):
            return {"status": "error", "error": "Internet access is disabled at system level."}

        # 5) Call model manager's generation API
        if not hasattr(self.model_manager, "generate"):
            return {"status": "error", "error": "Loaded model does not support generate()."}

        try:
            result = self.model_manager.generate(
                prompt=prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
                **kwargs
            )
        except Exception as e:
            return {"status": "error", "error": f"Model generation error: {e}"}

        elapsed = time.time() - start
        _safe_print(f"[engine] generate completed in {elapsed:.2f}s")
        return {"status": "ok", "result": result, "time_s": elapsed, "rag_used": bool(use_rag and rag_context)}

    # ---------- Streaming helper (best-effort) ----------
    def stream_generate(self, prompt: str, **kwargs):
        """
        If the underlying model_manager offers a streaming interface (yielding tokens/partial text),
        expose it directly. Otherwise, fall back to a single blocking generate() call.
        Usage: for chunk in engine.stream_generate(...): handle(chunk)
        """
        if hasattr(self.model_manager, "stream_generate"):
            for chunk in self.model_manager.stream_generate(prompt, **kwargs):
                yield chunk
            return

        # fallback: single-shot generate
        res = self.generate(prompt, **kwargs)
        yield res.get("result") if res.get("status") == "ok" else res

# ---------- CLI / Test harness ----------
def run_test_engine(model: Optional[str] = None, prompt: Optional[str] = None):
    _safe_print("PRIMUS Engine — self-test starting...")
    # instantiate engine
    try:
        eng = Engine(model_path=model)
    except Exception as e:
        _safe_print("[engine] Failed to create Engine:", e)
        return {"status": "error", "error": str(e)}

    status = eng.get_status()
    _safe_print("[engine] Status:", json.dumps(status, indent=2))

    test_prompt = prompt or "Write a friendly one-line greeting."
    _safe_print("[engine] Running generate test with prompt:", test_prompt)
    out = eng.generate(test_prompt, max_tokens=64)
    _safe_print("[engine] Test result:", out)
    return out


def _parse_cli_and_run():
    parser = argparse.ArgumentParser(prog="core/engine.py", description="PRIMUS Engine test runner")
    parser.add_argument("--test-engine", action="store_true", help="Run engine self-test")
    parser.add_argument("--model", type=str, help="Optional model path/name to load for test")
    parser.add_argument("--prompt", type=str, help="Optional prompt to use during test")
    args = parser.parse_args()

    if args.test_engine:
        _safe_print("Running engine self-test...")
        res = run_test_engine(model=args.model, prompt=args.prompt)
        if isinstance(res, dict) and res.get("status") == "ok":
            _safe_print("Engine self-test: PASS")
        else:
            _safe_print("Engine self-test: RESULT:", res)
    else:
        parser.print_help()


if __name__ == "__main__":
    _parse_cli_and_run()