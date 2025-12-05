# core/model_manager.py
"""
PRIMUS OS - Model Manager
Handles loading and running local GGUF models (llama.cpp backend).
Designed for LM Studio–compatible GGUF models.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


class LlamaCppBackend:
    """Minimal llama.cpp backend wrapper (local/offline only)."""

    def __init__(self, config: Dict[str, Any], logger: Optional[logging.Logger] = None):
        self._logger = logger or logging.getLogger("model_manager")
        self._llama = None
        self._available = False
        self._config = config
        self._init_error: Optional[str] = None

        try:
            from llama_cpp import Llama
        except Exception as exc:  # ImportError or runtime errors
            self._init_error = f"llama_cpp import failed: {exc}"
            self._logger.error(self._init_error)
            return

        model_path = Path(config.get("model_path", "")).expanduser()
        if not model_path.is_absolute():
            model_path = model_path.resolve()

        if not model_path.exists():
            self._init_error = f"Model file not found at {model_path}"
            self._logger.error(self._init_error)
            return

        try:
            self._llama = Llama(
                model_path=str(model_path),
                n_ctx=int(config.get("n_ctx", 4096)),
                n_threads=int(config.get("n_threads", 4)),
                temperature=float(config.get("temperature", 0.7)),
                top_p=float(config.get("top_p", 0.9)),
                verbose=False,
            )
            self._available = True
            self._logger.info("LlamaCpp backend initialized with model %s", model_path)
        except Exception as exc:
            self._init_error = f"Failed to load model: {exc}"
            self._logger.error(self._init_error)

    def is_available(self) -> bool:
        return self._available and self._llama is not None

    def generate(self, prompt: str, **kwargs) -> str:
        if not self.is_available():
            raise RuntimeError(self._init_error or "Model backend unavailable")

        max_tokens = kwargs.get("max_tokens", 128)
        temperature = kwargs.get("temperature", self._config.get("temperature", 0.7))
        top_p = kwargs.get("top_p", self._config.get("top_p", 0.9))
        stop = kwargs.get("stop")

        output = self._llama(
            prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            stop=stop,
        )
        try:
            return output["choices"][0]["text"]
        except Exception as exc:
            raise RuntimeError(f"Unexpected model output: {exc}")

    def status(self) -> Tuple[bool, str]:
        if self.is_available():
            return True, "Model loaded"
        return False, self._init_error or "Model backend unavailable"


class ModelManager:
    def __init__(self, system_root: Optional[str] = None, config_path: Optional[str] = None):
        self.system_root = Path(system_root) if system_root else Path(__file__).resolve().parents[1]
        default_config = self.system_root / "configs" / "model_config.json"
        self.config_path = Path(config_path) if config_path else default_config
        self.config_path.parent.mkdir(parents=True, exist_ok=True)

        self.logger = logging.getLogger("model_manager")
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter("%(asctime)s [model_manager] %(levelname)s: %(message)s"))
            self.logger.addHandler(handler)
        self.logger.setLevel(logging.INFO)

        self.config = self._load_or_create_config()
        self.backend = self._build_backend(self.config)

    # -----------------------------------------------------------
    # Config management
    # -----------------------------------------------------------
    def _load_or_create_config(self) -> Dict[str, Any]:
        if not self.config_path.exists():
            default = {
                "backend": "llama_cpp",
                "model_path": "C:\\Users\\amoki\\Desktop\\AI files\\models\\DarkIdol-Llama-3.1-8B-Instruct-1.3-Uncensored_Q4_K_M.gguf",
                "n_ctx": 4096,
                "n_threads": 8,
                "temperature": 0.7,
                "top_p": 0.9,
            }
            self.config_path.write_text(json.dumps(default, indent=2), encoding="utf-8")
            return default

        try:
            return json.loads(self.config_path.read_text(encoding="utf-8"))
        except Exception:
            # fallback to minimal default if file is corrupted
            default = {
                "backend": "llama_cpp",
                "model_path": "",
            }
            self.config_path.write_text(json.dumps(default, indent=2), encoding="utf-8")
            return default

    def _build_backend(self, config: Dict[str, Any]):
        backend_name = config.get("backend", "llama_cpp")
        if backend_name == "llama_cpp":
            return LlamaCppBackend(config, logger=self.logger)
        self.logger.error("Unsupported backend: %s", backend_name)
        return None

    # -----------------------------------------------------------
    # Public API
    # -----------------------------------------------------------
    def is_available(self) -> bool:
        return bool(self.backend and self.backend.is_available())

    def model_status_check(self) -> Tuple[bool, str]:
        if not self.backend:
            return False, "No backend configured"
        try:
            ok, message = self.backend.status()
        except Exception as exc:
            return False, f"Status check failed: {exc}"

        if not ok:
            return False, message

        # optional lightweight generation sanity check
        try:
            _ = self.backend.generate("ping", max_tokens=1)
        except Exception as exc:
            return False, f"Generation failed: {exc}"
        return True, "Model backend available"

    def generate(self, prompt: str, **kwargs) -> str:
        if not self.backend:
            raise RuntimeError("Model backend not configured")
        return self.backend.generate(prompt, **kwargs)

    def list_models(self) -> list:
        return [self.config.get("model_path", "")] if self.config else []


__all__ = ["ModelManager", "LlamaCppBackend"]
