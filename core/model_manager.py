# core/model_manager.py
"""
ModelManager for PRIMUS OS.

- Wraps a local llama.cpp backend (llama-cpp-python).
- Resolves model_path from:
    1) Explicit model_path argument, or
    2) configs/model_config.json -> {"model_path": "..."}
- Provides:
    - generate(prompt)  -> text
    - is_available()    -> bool
    - get_backend_status() -> (ok: bool, message: str)
    - list_models()     -> list of known model paths (for diagnostics)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from llama_cpp import Llama
except Exception:  # noqa: BLE001
    Llama = None  # type: ignore[assignment]

logger = logging.getLogger("model_manager")


class ModelManager:
    """
    Thin wrapper around a single local llama.cpp model.

    This is intentionally simple for PRIMUS v1:
    - Single GGUF model on disk.
    - Synchronous text completion via llama-cpp-python.
    """

    def __init__(
        self,
        model_path: Optional[str] = None,
        system_root: Optional[Path] = None,
        max_context_tokens: int = 4096,
    ) -> None:
        """
        Initialize the model manager.

        :param model_path: Optional explicit path to the GGUF model file.
        :param system_root: Optional System/ root; used to locate configs/.
        :param max_context_tokens: Context window for llama.cpp.
        """
        self.system_root = system_root or Path(__file__).resolve().parents[1]
        self.configs_dir = self.system_root / "configs"
        self.model_path: Optional[Path] = None
        self.max_context_tokens = max_context_tokens

        self._llm: Optional[Llama] = None  # type: ignore[assignment]

        # Resolve model path from explicit argument or config
        resolved_path = self._resolve_model_path(model_path)
        if resolved_path is None:
            logger.error(
                "ModelManager could not resolve a valid model path; "
                "backend will be unavailable."
            )
            return

        self.model_path = resolved_path

        # Try to initialize llama.cpp backend
        self._initialize_backend()

    # ------------------------------------------------------------------
    # Path / config helpers
    # ------------------------------------------------------------------

    def _resolve_model_path(self, explicit_path: Optional[str]) -> Optional[Path]:
        """Resolve the model path from explicit arg or configs/model_config.json."""
        if explicit_path:
            path = Path(explicit_path).expanduser()
            if path.is_file():
                return path
            logger.error("Explicit model_path does not exist: %s", path)
            return None

        # Fall back to configs/model_config.json
        cfg_path = self.configs_dir / "model_config.json"
        if not cfg_path.is_file():
            logger.error(
                "No model_path provided and %s does not exist; "
                "please create configs/model_config.json with a 'model_path' key.",
                cfg_path,
            )
            return None

        try:
            with cfg_path.open("r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to read %s: %s", cfg_path, exc)
            return None

        mp = cfg.get("model_path")
        if not mp:
            logger.error(
                "configs/model_config.json is missing 'model_path' key: %s",
                cfg_path,
            )
            return None

        path = Path(mp).expanduser()
        if not path.is_file():
            logger.error(
                "Model path from config does not exist: %s (config=%s)",
                path,
                cfg_path,
            )
            return None

        return path

    # ------------------------------------------------------------------
    # Backend initialization
    # ------------------------------------------------------------------

    def _initialize_backend(self) -> None:
        """
        Initialize the llama.cpp backend if possible.

        If llama_cpp is not installed or the model path is invalid, the backend
        remains unavailable but ModelManager stays importable.
        """
        if self.model_path is None:
            logger.warning("Cannot initialize backend: model_path is None.")
            return

        if Llama is None:
            logger.warning(
                "llama_cpp is not available; install 'llama-cpp-python' in this venv."
            )
            return

        try:
            self._llm = Llama(
                model_path=str(self.model_path),
                n_ctx=self.max_context_tokens,
                logits_all=False,
                embedding=False,
            )
            logger.info(
                "LlamaCpp backend initialized with model %s",
                self.model_path,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to initialize LlamaCpp backend: %s", exc)
            self._llm = None

    # ------------------------------------------------------------------
    # Public API used by PrimusCore / runtime
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        """Return True if a llama.cpp backend is ready."""
        return self._llm is not None and self.model_path is not None

    def generate(
        self,
        prompt: str,
        max_tokens: int = 256,
        temperature: float = 0.7,
        top_p: float = 0.9,
        stop: Optional[List[str]] = None,
    ) -> str:
        """
        Generate a completion from the local model.

        This is a simple text-completion interface, not full chat formatting.
        """
        if not self.is_available():
            raise RuntimeError("Model backend is not available; cannot generate text.")

        stop = stop or ["User:", "Assistant:"]
        assert self._llm is not None  # for type checkers

        logger.debug(
            "ModelManager.generate called (len(prompt)=%d, max_tokens=%d)",
            len(prompt),
            max_tokens,
        )

        try:
            result: Dict[str, Any] = self._llm(
                prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
                stop=stop,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Error during llama.cpp generation: %s", exc)
            raise

        # Newer llama_cpp returns a dict with 'choices'
        text = ""
        try:
            choices = result.get("choices") or []
            if choices:
                text = choices[0].get("text", "")
        except Exception:  # noqa: BLE001
            # Fallback: some versions may behave slightly differently
            logger.warning("Unexpected llama_cpp response format: %r", result)

        return text.strip()

    def get_backend_status(self) -> Tuple[bool, str]:
        """
        Return a (ok, message) tuple for bootup tests.

        PrimusCore's model_status_check uses this if present.
        """
        if self.model_path is None:
            return False, "No model_path resolved."

        if self._llm is None:
            return False, f"llama_cpp backend not initialized for {self.model_path}"

        return True, f"llama.cpp model loaded from {self.model_path}"

    def list_models(self) -> List[str]:
        """
        Return a list of known/active model paths for diagnostics.

        For now, this is just the single active model if any.
        """
        if self.model_path is None:
            return []
        return [str(self.model_path)]


# Convenience accessor (mirrors style of other managers)
_singleton_model_manager: Optional[ModelManager] = None


def get_model_manager(
    model_path: Optional[str] = None,
    system_root: Optional[Path] = None,
) -> ModelManager:
    """
    Return a singleton ModelManager instance.

    PrimusCore may call this or instantiate ModelManager directly.
    """
    global _singleton_model_manager
    if _singleton_model_manager is None:
        _singleton_model_manager = ModelManager(
            model_path=model_path,
            system_root=system_root,
        )
    return _singleton_model_manager