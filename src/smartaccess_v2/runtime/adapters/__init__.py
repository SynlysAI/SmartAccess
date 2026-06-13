"""SmartAccess v2 运行时适配器。"""

from .artifact_store import FileArtifactStore, InMemoryArtifactStore
from .ai_generator import SmartAccessAiGenerator
from .automation_stub import StubAutomationProvider
from .platform_stub import StubPlatformClient
from .vision_stub import StubVisionProvider
from .win32_automation import Win32AutomationProvider

__all__ = [
    "FileArtifactStore",
    "InMemoryArtifactStore",
    "SmartAccessAiGenerator",
    "StubAutomationProvider",
    "StubPlatformClient",
    "StubVisionProvider",
    "Win32AutomationProvider",
]
