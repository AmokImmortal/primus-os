"""
core.model_manager
~~~~~~~~~~~~~~~~~~

Centralized model management for P.R.I.M.U.S.

Responsibilities:
- Resolve and validate the local model path.
- Lazily construct and cache the llama.cpp backend.
- Provide simple health / self-test information for bootup checks.
- Offer a stable access point for other components (SubchatEngine, CLI, etc.).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

# External dependency: llama_cpp (or llamafile-compatible bindings)
try:
    from llama_cpp import Llama  # type: ignore
except Exception:  # pragma: no cover - handled gracefully in code
    Llama = None  # type: ignore

logger = logging.getLogger(__name__)

# Environment variable used when no model_path is passed explicitly.
ENV_MODEL_PATH = "PRIMUS_MODEL_PATH"
ENV_CONTEXT_SIZE = "PRIMUS_CONTEXT_SIZE"


class ModelManager:
    """
    Manages the lifecycle and basic health of the local LLM backend.

    Public surface intentionally small and stable so other components can
    depend on it without tight coupling:

    - constructor accepts `model_path` (used by PrimusCore).
    - `get_backend()` / `get_model()` / `get_chat_model()` all return
      the underlying llama.cpp object.
    - `check_backend()` is used by PrimusRuntime bootup tests and returns
      (ok: bool, message: str).
    - `run_self_test()` returns a dict so PrimusCore can splat it into
      the core self-test results.
    """

    def __init__(
        self,
        model_path: Optional[str | Path] = None,
        *,
        n_ctx: Optional[int] = None,
    ) -> None:
        """
        Initialize the manager; backend is *not* created until first use.

        Args:
            model_path:
                Optional explicit path to the GGUF model. If not provided,
                ENV_MODEL_PATH will be used. If neither is available, a
                ValueError is raised when the backend is first requested.
            n_ctx:
                Optional context length override. If not provided, we try
                ENV_CONTEXT_SIZE, falling back to a safe default (4096).
        """
        self._raw_model_path = model_path
        self._backend = None  # type: ignore[assignment]
        self._n_ctx_override = n_ctx

        resolved_path = self._resolve_model_path(raise_on_missing=False)
        if resolved_path is not None:
            logger.debug("ModelManager configured with model_path=%s", resolved_path)
        else:
            logger.warning(
                "ModelManager initialized without a model path. "
                "Set %s or pass model_path explicitly before use.",
                ENV_MODEL_PATH,
            )

        logger.info("ModelManager initialized.")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _resolve_model_path(self, raise_on_missing: bool = True) -> Optional[Path]:
        """
        Determine the model path from explicit argument or environment.

        Returns:
            Path if available, otherwise None (unless raise_on_missing=True).

        Raises:
            ValueError: if no path can be resolved and raise_on_missing is True.
        """
        # Priority: explicit argument beats env.
        if self._raw_model_path is not None:
            path = Path(self._raw_model_path)
        else:
            env_val = os.getenv(ENV_MODEL_PATH)
            path = Path(env_val) if env_val else None

        if path is None:
            if raise_on_missing:
                raise ValueError(
                    f"No model path provided. Set {ENV_MODEL_PATH} or pass model_path."
                )
            return None

        if not path.exists():
            msg = f"Configured model path does not exist: {path}"
            if raise_on_missing:
                raise ValueError(msg)
            logger.warning(msg)
            return None

        return path

    def _get_n_ctx(self) -> int:
        """
        Resolve context length from override, env, or default.
        """
        if self._n_ctx_override is not None:
            return self._n_ctx_override

        env_val = os.getenv(ENV_CONTEXT_SIZE)
        if env_val:
            try:
                return max(512, int(env_val))
            except ValueError:
                logger.warning(
                    "Invalid %s=%r; falling back to default context size.",
                    ENV_CONTEXT_SIZE,
                    env_val,
                )

        # Reasonable default that matches how the model is currently used.
        return 4096

    def _create_backend(self) -> Any:
        """
        Instantiate the llama.cpp backend.

        Returns:
            An instance of llama_cpp.Llama (or compatible) configured with the
            resolved model path.

        Raises:
            RuntimeError: if llama_cpp is not available or model path invalid.
        """
        if Llama is None:
            raise RuntimeError(
                "llama_cpp is not available. Ensure the 'llama-cpp-python' "
                "package (or compatible bindings) is installed."
            )

        model_path = self._resolve_model_path(raise_on_missing=True)
        assert model_path is not None  # for type checkers

        n_ctx = self._get_n_ctx()

        logger.info(
            "Initializing llama.cpp backend (model=%s, n_ctx=%d)...",
            model_path,
            n_ctx,
        )

        backend = Llama(
            model_path=str(model_path),
            n_ctx=n_ctx,
            # Keep other options minimal and conservative; can be
            # surfaced via config later if needed.
            logits_all=False,
            embedding=False,
        )

        logger.info("LlamaCpp backend initialized with model %s", model_path)
        return backend

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def get_backend(self) -> Any:
        """
        Return the cached backend instance, constructing it lazily if needed.

        This is the canonical way for other components to obtain the model.
        """
        if self._backend is None:
            try:
                self._backend = self._create_backend()
            except Exception as exc:  # pragma: no cover - defensive
                logger.exception("Failed to initialize model backend: %s", exc)
                raise
        return self._backend

    # Friendly aliases for other components that might use different names
    get_model = get_backend
    get_chat_model = get_backend

    def check_backend(self) -> Tuple[bool, str]:
        """
        Lightweight health check used by PrimusRuntime bootup tests.

        Returns:
            (ok, message) where ok indicates whether the backend could be
            initialized and message is a human-readable summary.
        """
        try:
            backend = self.get_backend()
        except Exception as exc:
            msg = f"failed to initialize model backend: {exc}"
            logger.error("Model backend check failed: %s", msg)
            return False, msg

        # If we got here, backend exists; optionally we could add a trivial
        # call to ensure it responds, but that's usually unnecessary.
        model_path = self._resolve_model_path(raise_on_missing=False)
        if model_path is None:
            msg = "llama.cpp model loaded (path unknown)"
        else:
            msg = f"llama.cpp model loaded from {model_path}"

        logger.debug("Model backend check succeeded: %s", msg)
        return True, msg

    def run_self_test(self) -> Dict[str, Any]:
        """
        Deeper self-test used by PrimusCore.run_self_test().

        IMPORTANT: this must return a *dict*, not a tuple, because
        PrimusCore expands it with `{"status": "ok", **status}`.

        Returns:
            A dict summarizing backend health, suitable for inclusion in
            the core self-test summary.
        """
        ok, msg = self.check_backend()
        result: Dict[str, Any] = {
            "backend_ok": ok,
            "backend_message": msg,
        }

        # Include a couple of lightweight details when available.
        if ok:
            try:
                backend = self.get_backend()
                # Many llama_cpp builds expose `.n_ctx` and `.vocab_size`.
                n_ctx = getattr(backend, "n_ctx", None)
                vocab_size = getattr(backend, "vocab_size", None)
                if n_ctx is not None:
                    result["n_ctx"] = int(n_ctx)
                if vocab_size is not None:
                    result["vocab_size"] = int(vocab_size)
            except Exception as exc:  # pragma: no cover - defensive
                logger.debug("Non-fatal error querying backend metadata: %s", exc)

        return result

    def get_status(self) -> Dict[str, Any]:
        """
        Convenience status wrapper; currently just delegates to run_self_test().

        Primarily here to give other components a stable, dictionary-shaped
        status view.
        """
        return self.run_self_test()