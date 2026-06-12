"""Small workspace-scoped runtime preferences."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


AI_PROFILE_WORKFLOW = "workflow"
AI_PROFILE_DEVICE_ONBOARDING = "device_onboarding"
AI_PROFILE_PURPOSES = (AI_PROFILE_WORKFLOW, AI_PROFILE_DEVICE_ONBOARDING)
FIXED_DEVICE_ONBOARDING_AI_PROFILE = "codex"


class WorkspaceSettingsStore:
    """Persists non-secret preferences under ``workspace/config``."""

    def __init__(self, *, workspace_dir: Path) -> None:
        self._path = Path(workspace_dir) / "config" / "app_settings.json"

    @property
    def path(self) -> Path:
        return self._path

    def ai_profile_preferences(self) -> dict[str, str]:
        settings = self._read()
        raw = settings.get("ai_profiles")
        preferences = raw if isinstance(raw, dict) else {}
        return {
            purpose: str(preferences.get(purpose) or "")
            for purpose in AI_PROFILE_PURPOSES
        }

    def set_ai_profile_preference(self, purpose: str, profile_id: str) -> dict[str, str]:
        if purpose not in AI_PROFILE_PURPOSES:
            raise ValueError(f"Unsupported AI profile purpose: {purpose}")
        settings = self._read()
        raw = settings.get("ai_profiles")
        preferences = dict(raw) if isinstance(raw, dict) else {}
        preferences[purpose] = profile_id
        settings["ai_profiles"] = preferences
        self._write(settings)
        return self.ai_profile_preferences()

    def _read(self) -> dict[str, Any]:
        if not self._path.exists():
            return {}
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def _write(self, settings: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(settings, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
