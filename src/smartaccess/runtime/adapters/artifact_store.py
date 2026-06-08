"""Artifact stores: where screenshots, logs, and run traces land.

``FileArtifactStore`` writes under ``workspace/runs/{session_id}/`` so a run
produces real, inspectable files (run_trace.jsonl, screenshots, logs).
``InMemoryArtifactStore`` keeps everything in memory for fast tests.
"""

from __future__ import annotations

from pathlib import Path


class FileArtifactStore:
    """Persists run artifacts under the workspace runs directory."""

    def __init__(self, workspace_dir: str | Path) -> None:
        self._workspace_dir = Path(workspace_dir)

    def _session_dir(self, session_id: str) -> Path:
        path = self._workspace_dir / "runs" / session_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def save_screenshot(self, session_id: str, name: str, data: bytes) -> str:
        path = self._session_dir(session_id) / "screenshots" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return str(path)

    def save_text(self, session_id: str, name: str, text: str) -> str:
        path = self._session_dir(session_id) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return str(path)

    def append_jsonl(self, session_id: str, name: str, line: str) -> str:
        path = self._session_dir(session_id) / name
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(line)
            handle.write("\n")
        return str(path)


class InMemoryArtifactStore:
    """Keeps artifacts in memory; useful for fast, isolated tests."""

    def __init__(self) -> None:
        self.screenshots: dict[str, bytes] = {}
        self.texts: dict[str, str] = {}
        self.jsonl: dict[str, list[str]] = {}

    def save_screenshot(self, session_id: str, name: str, data: bytes) -> str:
        key = f"{session_id}/screenshots/{name}"
        self.screenshots[key] = data
        return key

    def save_text(self, session_id: str, name: str, text: str) -> str:
        key = f"{session_id}/{name}"
        self.texts[key] = text
        return key

    def append_jsonl(self, session_id: str, name: str, line: str) -> str:
        key = f"{session_id}/{name}"
        self.jsonl.setdefault(key, []).append(line)
        return key
