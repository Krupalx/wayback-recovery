"""
Resume state tracking.

Keeps a JSON file of which URLs have been successfully downloaded and which
ones failed (with reasons). On restart, already-completed URLs are skipped
automatically.
"""

import json
from pathlib import Path
from dataclasses import dataclass, field


@dataclass
class DownloadState:
    state_file: Path
    completed: set[str] = field(default_factory=set)
    failed: dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        if self.state_file.exists():
            data = json.loads(self.state_file.read_text())
            self.completed = set(data.get("completed", []))
            self.failed = data.get("failed", {})

    def mark_done(self, url: str) -> None:
        self.completed.add(url)
        self.failed.pop(url, None)
        self._save()

    def mark_failed(self, url: str, reason: str) -> None:
        self.failed[url] = reason
        self._save()

    def is_done(self, url: str) -> bool:
        return url in self.completed

    def _save(self) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "completed": sorted(self.completed),
            "failed": self.failed,
        }
        self.state_file.write_text(json.dumps(data, indent=2))

    @property
    def stats(self) -> dict[str, int]:
        return {"completed": len(self.completed), "failed": len(self.failed)}
