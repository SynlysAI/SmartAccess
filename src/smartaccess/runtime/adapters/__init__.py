"""SmartAccess 运行时适配器。"""

from .artifact_store import FileArtifactStore, InMemoryArtifactStore
from .ai_generator import SmartAccessAiGenerator
from .automation_stub import StubAutomationProvider
from .inmemory import EchoInstructionGenerator, StubProcessExecutorClient
from .local_vision import LocalVisionProvider
from .platform_stub import StubPlatformClient
from .process_signal import UdpProcessExecutorClient
from .speclabos_client import SpecLabOSPlatformClient
from .api_vision import ApiVisionProvider
from .vision_stub import StubVisionProvider
from .win32_automation import Win32AutomationProvider

__all__ = [
    "EchoInstructionGenerator",
    "FileArtifactStore",
    "InMemoryArtifactStore",
    "ApiVisionProvider",
    "LocalVisionProvider",
    "SmartAccessAiGenerator",
    "SpecLabOSPlatformClient",
    "StubAutomationProvider",
    "StubPlatformClient",
    "StubProcessExecutorClient",
    "StubVisionProvider",
    "UdpProcessExecutorClient",
    "Win32AutomationProvider",
]
