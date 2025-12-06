#!/usr/bin/env python3
"""
core.model_manager

Thin wrapper around a llama.cpp backend used by PrimusCore / PrimusRuntime.

Responsibilities:
- Discover a GGUF model path (env PRIMUS_MODEL_PATH or explicit arg).
- Lazily load a llama.cpp Llama instance.
- Provide a simple `generate(prompt, ...) -> str` API.
- Provide `get_backend_status() -> tuple[bool, str]` for bootup tests.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


try:
    # llama-cpp-python backend
    from llama_cpp import Llama  # type: ignore[import]
except Exception:  # noqa: BLE001
    Llama = None  # type: ignore[assignment]
    logger.warning("llama_cpp not available; ModelManager will run in 'no-backend' mode.")


class ModelManager:
    """
    Wraps a llama.cpp model and exposes a minimal generation API.
    """

    def __init__(
        self,
        model_path: Optional[str] = None,
        n_ctx: int = 4096,
        n_threads: Optional[int] = None,
    ) -> None:
        self.model_path: Optional[str] = model_path or os.getenv("PRIMUS_MODEL_PATH")
        self.n_ctx = n_ctx
        self.n_threads = n_threads or (os.cpu_count() or 4)

        self._llama: Optional[Llama] = None  # type: ignore[type-arg]
        self._init_error: Optional[str] = None

        if not self.model_path:
            logger.warning(
                "ModelManager initialized without a model path. "
                "Set PRIMUS_MODEL_PATH or pass model_path explicitly before use."
            )
            return

        if Llama is None:
            self._init_error = "llama_cpp backend not installed or failed to import."
            logger.error("ModelManager cannot initialize: %s", self._init_error)
            return

        try:
            logger.info(
                "Initializing llama.cpp backend with model %s (n_ctx=%d, n_threads=%d)",
                self.model_path,
                self.n_ctx,
                self.n_threads,
            )
            self._llama = Llama(
                model_path=self.model_path,
                n_ctx=self.n_ctx,
                n_threads=self.n_threads,
                logits_all=False,
                vocab_only=False,
            )
            logger.info("LlamaCpp backend initialized with model %s", self.model_path)
        except Exception as exc:  # noqa: BLE001
            self._init_error = f"Failed to initialize Llama backend: {exc}"
            self._llama = None
            logger.exception("Error initializing llama.cpp backend: %s", exc)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def has_backend(self) -> bool:
        """Return True if a model backend is ready for generation."""
        return self._llama is not None

    def generate(
        self,
        prompt: str,
        max_tokens: int = 256,
        temperature: float = 0.7,
        top_p: float = 0.95,
        stop: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> str:
        """
        Run a completion on the underlying llama.cpp model and return text only.
        """
        if self._llama is None:
            if not self.model_path:
                raise RuntimeError(
                    "Model backend not initialized: no model_path configured. "
                    "Set PRIMUS_MODEL_PATH or re-create ModelManager with model_path."
                )
            if self._init_error:
                raise RuntimeError(f"Model backend initialization failed: {self._init_error}")
            raise RuntimeError("Model backend is not available.")

        stop_tokens = stop or ["<|end_of_text|>", "<|eot_id|>"]

        logger.info(
            "ModelManager.generate(prompt_len=%d, max_tokens=%d, temp=%.2f, top_p=%.2f)",
            len(prompt),
            max_tokens,
            temperature,
            top_p,
        )

        result: Dict[str, Any] = self._llama(
            prompt=prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            stop=stop_tokens,
            echo=False,
            **kwargs,
        )

        choices = result.get("choices") or []
        if not choices:
            logger.warning("ModelManager.generate received empty choices from backend.")
            return ""

        text = choices[0].get("text", "")
        return text.strip()

    def get_backend_status(self) -> Tuple[bool, str]:
        """
        Status hook used by PrimusRuntime.run_bootup_test().

        Returns:
            (ok: bool, message: str)
        """
        if self._llama is not None:
            return True, f"llama.cpp model loaded from {self.model_path}"

        if not self.model_path:
            return False, "No model configured (PRIMUS_MODEL_PATH not set and no model_path passed)."

        if self._init_error:
            return False, f"Model backend failed to initialize: {self._init_error}"

        return False, "Model backend not available for unknown reasons."


__all__ = ["ModelManager"]