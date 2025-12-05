import json
import time
import uuid
from pathlib import Path


class JournalStore:
    """
    Private Captain’s Log journal. Stored as JSONL file.
    Absolutely inaccessible outside Captain’s Log mode.
    """

    def __init__(self, journal_path: Path):
        self.journal_path = journal_path
        self.journal_path.parent.mkdir(parents=True, exist_ok=True)

    def add_entry(self, text: str, mode: str):
        entry = {
            "id": str(uuid.uuid4()),
            "timestamp": time.time(),
            "mode": mode,
            "text": text,
        }

        with open(self.journal_path, "a", encoding="utf8") as f:
            f.write(json.dumps(entry) + "\n")

        return entry["id"]

    def list_entries(self):
        if not self.journal_path.exists():
            return []

        out = []
        with open(self.journal_path, "r", encoding="utf8") as f:
            for line in f:
                try:
                    out.append(json.loads(line.strip()))
                except json.JSONDecodeError:
                    continue
        return out

    def clear(self):
        if self.journal_path.exists():
            self.journal_path.unlink()