import os
import json
import time
import hashlib
from typing import Optional
from pathlib import Path


class CaptainsLogManager:
    """
    Backend engine for Captain's Log Sandbox Mode.
    Handles:
        - Password/PIN gate
        - Sandbox isolation (no logging unless explicitly enabled)
        - Internal Captain’s Log RAG access
        - Permission-gated personality/system modifications
        - Secure root-control context that ONLY activates in sandbox mode
    """

    def __init__(self, root_path: str):
        self.root = Path(root_path)
        self.config_path = self.root / "captains_log" / "config.json"
        self.rag_path = self.root / "captains_log" / "rag"
        self.session_active = False
        self.allow_logging = False  # logging OFF by default in sandbox
        self.root_control_enabled = False  # full root control ONLY inside sandbox AND only after override

        self._ensure_structure()

    # -------------------------------------------------------
    # Structure + Config Setup
    # -------------------------------------------------------

    def _ensure_structure(self):
        """Ensures required folders/files exist."""
        cl_root = self.root / "captains_log"
        cl_root.mkdir(exist_ok=True)

        self.rag_path.mkdir(exist_ok=True)

        if not self.config_path.exists():
            self._write_config({
                "password_hash": None,
                "security_questions": {}
            })

    def _read_config(self) -> dict:
        with open(self.config_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _write_config(self, cfg: dict):
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=4)

    # -------------------------------------------------------
    # Password / PIN Setup & Verification
    # -------------------------------------------------------

    @staticmethod
    def _hash(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def set_password(self, password: str, security_questions: dict):
        """
        password: 4+ digit PIN or 6+ char password
        security_questions: dict of {"question": "answer"}
        """
        if len(password) < 4:
            raise ValueError("Password/PIN must be at least 4 characters long.")

        cfg = self._read_config()
        cfg["password_hash"] = self._hash(password)
        cfg["security_questions"] = {q: self._hash(a.lower()) for q, a in security_questions.items()}
        self._write_config(cfg)

    def verify_password(self, password: str) -> bool:
        cfg = self._read_config()
        if not cfg["password_hash"]:
            return False
        return cfg["password_hash"] == self._hash(password)

    def reset_password(self, answers: dict, new_password: str) -> bool:
        """
        answers: {"question": "answer"} for at least 2 of 3 questions.
        """
        cfg = self._read_config()
        stored = cfg.get("security_questions", {})
        correct = 0

        for q, a in answers.items():
            if q in stored and stored[q] == self._hash(a.lower()):
                correct += 1

        if correct < 2:
            return False

        self.set_password(new_password, cfg["security_questions"])
        return True

    # -------------------------------------------------------
    # Sandbox Session Controls
    # -------------------------------------------------------

    def enter_sandbox(self, password: str) -> bool:
        """
        Enter Captain's Log sandbox mode.
        Enables isolation and root-control environment.
        """
        if not self.verify_password(password):
            return False

        self.session_active = True
        self.root_control_enabled = True  # gives full system control

        # logging is *disabled* unless user explicitly enables it
        self.allow_logging = False

        return True

    def exit_sandbox(self):
        """Exit sandbox mode — disables root control and restores safe defaults."""
        self.session_active = False
        self.root_control_enabled = False
        self.allow_logging = False

    # -------------------------------------------------------
    # Logging Control (OFF by default in sandbox)
    # -------------------------------------------------------

    def enable_logging(self):
        if not self.session_active:
            raise PermissionError("Cannot enable logging outside sandbox mode.")
        self.allow_logging = True

    def disable_logging(self):
        self.allow_logging = False

    # -------------------------------------------------------
    # Captain’s Log RAG Access
    # -------------------------------------------------------

    def write_rag_entry(self, filename: str, content: str):
        """
        Only allowed INSIDE sandbox.
        These entries are unreadable by normal Primus runtime.
        """
        if not self.session_active:
            raise PermissionError("RAG write denied — sandbox is not active.")

        path = self.rag_path / filename
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    def read_rag_entry(self, filename: str) -> Optional[str]:
        if not self.session_active:
            raise PermissionError("RAG read denied — sandbox is not active.")

        path = self.rag_path / filename
        if not path.exists():
            return None

        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    # -------------------------------------------------------
    # System / Personality Modification Controls
    # -------------------------------------------------------

    def request_modification(self, description: str) -> dict:
        """
        Before Primus can perform ANY self-modification,
        it must send a request here and wait for YOUR approval.
        """
        if not self.session_active:
            return {"approved": False, "reason": "Not in sandbox mode."}

        return {
            "approved": None,  # to be filled by user
            "description": description,
            "timestamp": time.time()
        }

    def apply_modification(self, approved: bool, action):
        """
        Executes the modification ONLY if approved is True.
        "action" is a callable passed from Primus.
        """
        if not self.session_active or not self.root_control_enabled:
            raise PermissionError("Modification denied — sandbox not active.")

        if approved:
            return action()
        else:
            return "Modification rejected by user."

    # -------------------------------------------------------
    # Safety Checks
    # -------------------------------------------------------

    def is_sandbox_active(self) -> bool:
        return self.session_active

    def has_root_control(self) -> bool:
        """
        Root control ONLY exists inside sandbox.
        """
        return self.root_control_enabled

    def can_log(self) -> bool:
        """
        Returns whether sandbox logging is enabled.
        """
        return self.allow_logging